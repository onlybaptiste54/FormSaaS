"""Guided, form-independent sales funnels and their public journey."""

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator
from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .luna import LunaAPIError, merge_page_region, revise_page, slugify
from .models import Campaign, Company, Page, PageVersion, Tunnel, TunnelEvent, User
from .page_document import prepare_page, render_page, same_document
from .security import client_ip, current_user, rate_limit, write_user


router = APIRouter()

# Les trois routes du parcours public ecrivent en base a chaque appel. La
# deduplication borne les lignes d'une session, mais fabriquer des sessions
# neuves est gratuit : sans plafond, un script gonfle les compteurs et fait
# grossir tunnel_events sans fin. Un seul seau pour les trois, sinon le budget
# serait triple. Large : un parcours honnete coute trois a cinq appels.
JOURNEY_CALLS, JOURNEY_WINDOW = 120, 10 * 60

SALES_PAGE_INSTRUCTIONS = """Tu es Luna, directrice artistique et conceptrice de tunnels de vente.
Tu produis exclusivement le JSON demandé : message, html et region. Le HTML est un document complet, en français, avec un seul bloc <style> et une composition responsive soignée. Utilise la marque et le brief commercial fournis ; ne crée ni témoignage, ni chiffre, ni garantie, ni certification non fournis. Les pages s'adressent aux visiteurs, sans commentaire sur ton travail. Aucun script, iframe, formulaire, lien de paiement inventé ou ressource externe non fournie. Une image ne peut provenir que de identity.images. Balise les sections avec data-sillage-region. Sur la page d'ouverture, termine par un bouton <button type="button" data-sillage-next>Découvrir l'offre</button>. Sur la page d'offre, termine par un bouton <button type="button" data-sillage-goal>...</button> dont le libellé reprend exactement l'action du brief. Le serveur gère ces actions ; ne leur mets aucune URL. Pour une retouche, garde tout le reste de la page, et réponds avec html vide si la demande est une simple question. Une région partielle doit contenir sa balise racine complète ; region="style" contient le bloc style complet."""


class SalesTunnelCreate(BaseModel):
    name: str = Field(min_length=3, max_length=140)
    offer: str = Field(min_length=10, max_length=500)
    audience: str = Field(min_length=10, max_length=300)
    benefits: list[str] = Field(min_length=1, max_length=5)
    proof: str = Field(default="", max_length=500)
    tone: str = Field(default="", max_length=120)
    goal_label: str = Field(min_length=3, max_length=100)
    goal_url: str = Field(max_length=2048)
    website_url: str = Field(default="", max_length=300)

    @field_validator("name", "offer", "audience", "proof", "tone", "goal_label")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("benefits")
    @classmethod
    def check_benefits(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item or len(item) > 180 for item in cleaned):
            raise ValueError("Chaque point fort doit contenir entre 1 et 180 caractères.")
        return cleaned

    @field_validator("goal_url", "website_url")
    @classmethod
    def https_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return value
        try:
            parsed = AnyHttpUrl(value)
        except ValueError as exc:
            raise ValueError("Saisissez une adresse HTTPS valide.") from exc
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise ValueError("L'adresse doit utiliser HTTPS sans identifiants.")
        return str(parsed)

    @field_validator("goal_url")
    @classmethod
    def required_destination(cls, value: str) -> str:
        if not value:
            raise ValueError("Indiquez où doit mener le bouton final.")
        return value


class SalesPageRefine(BaseModel):
    instruction: str = Field(min_length=3, max_length=800)


class SalesDestinationUpdate(BaseModel):
    goal_url: str = Field(max_length=2048)

    @field_validator("goal_url")
    @classmethod
    def https_url(cls, value: str) -> str:
        return SalesTunnelCreate.https_url(SalesTunnelCreate.required_destination(value.strip()))


class SalesJourneyStart(BaseModel):
    source: str = Field(default="Lien direct", max_length=80)


def owned_tunnel(tunnel_id: str, db: Session, user: User) -> Tunnel:
    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel or tunnel.kind != "sales" or tunnel.campaign.company_id != user.company_id:
        raise HTTPException(404, "Tunnel introuvable")
    return tunnel


def page_payload(page: Page, *, draft: bool = False) -> dict:
    html = page.draft_html if draft and page.draft_html else page.html
    return {"id": page.id, "name": page.name, "role": page.role, "position": page.position,
            "next_page_id": page.next_page_id, "html": render_page(html, ""),
            "has_draft": page.draft_html is not None, "visits": page.visits, "conversions": page.conversions}


def tunnel_payload(tunnel: Tunnel) -> dict:
    pages = sorted(tunnel.pages, key=lambda page: page.position)
    return {"id": tunnel.id, "name": tunnel.name, "slug": tunnel.slug, "status": tunnel.status,
            "kind": tunnel.kind, "brief": tunnel.brief or {}, "goal_label": tunnel.goal_label,
            "goal_url": tunnel.goal_url, "entry_page_id": tunnel.entry_page_id,
            "pages": [page_payload(page, draft=True) for page in pages]}


def brand_identity(company: Company) -> dict:
    identity = {"name": company.name, "sector": company.sector, "tone": company.tone,
                "primary_color": company.primary_color, "accent_color": company.accent_color,
                "brand": company.brand or {}}
    if company.logo:
        identity["images"] = [{"url": company.logo, "alt": f"Logo de {company.name}"}]
    return identity


class _SalesActionCheck(HTMLParser):
    def __init__(self, action: str) -> None:
        super().__init__()
        self.action = action
        self.valid_button = False
        self.has_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"form", "input", "select", "textarea"}:
            self.has_form = True
        if tag == "button" and self.action in values and "disabled" not in values:
            self.valid_button = True


def validate_sales_page(html: str, role: str) -> None:
    action = "data-sillage-next" if role == "landing" else "data-sillage-goal"
    checker = _SalesActionCheck(action)
    checker.feed(html)
    other_action = "data-sillage-goal" if role == "landing" else "data-sillage-next"
    other = _SalesActionCheck(other_action)
    other.feed(html)
    if not checker.valid_button or checker.has_form or other.valid_button:
        raise ValueError("La page doit comporter un bouton d'action actif, sans formulaire.")


def generate_step(role: str, data: SalesTunnelCreate, identity: dict) -> tuple[str, list[dict]]:
    instruction = (
        "Crée la première page du tunnel : une accroche forte qui présente le besoin, la promesse "
        "et les points forts vérifiés, puis invite à découvrir l'offre."
        if role == "landing" else
        "Crée la page d'offre : explique concrètement l'offre, réponds aux objections que le brief permet "
        f"de traiter, puis termine par l'action « {data.goal_label} »."
    )
    result = revise_page(
        "", instruction, identity,
        selection={"view": role, "page_role": role, "element_ids": [], "label": "Nouvelle page"},
        brief=data.model_dump(), api_key=settings.openai_api_key, model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds, page_instructions=SALES_PAGE_INSTRUCTIONS,
    )
    if result["region"] is not None:
        raise ValueError("Luna doit créer une page entière.")
    html, manifest = prepare_page(result["html"], require_form=False)
    validate_sales_page(html, role)
    if manifest:
        raise ValueError("Cette étape ne doit pas collecter de données personnelles.")
    return html, manifest


@router.get("/api/sales-funnels")
def list_sales_funnels(db: Session = Depends(get_db), user: User = Depends(current_user)):
    tunnels = db.scalars(select(Tunnel).join(Campaign).where(
        Campaign.company_id == user.company_id, Tunnel.kind == "sales", Campaign.archived.is_(False)
    ).order_by(desc(Tunnel.updated_at))).all()
    return [tunnel_payload(tunnel) for tunnel in tunnels]


@router.get("/api/sales-funnels/overview")
def sales_overview(db: Session = Depends(get_db), user: User = Depends(current_user)):
    since = datetime.combine(datetime.now(timezone.utc).date() - timedelta(days=29),
                             datetime.min.time(), timezone.utc)
    counts = db.execute(select(Tunnel.status, func.count(Tunnel.id)).join(Campaign).where(
        Campaign.company_id == user.company_id, Campaign.archived.is_(False),
        Tunnel.kind == "sales").group_by(Tunnel.status)).all()
    statuses = dict(counts)
    events = db.execute(select(TunnelEvent.kind, func.count(TunnelEvent.id))
                        .join(Tunnel, TunnelEvent.tunnel_id == Tunnel.id)
                        .join(Campaign, Tunnel.campaign_id == Campaign.id)
                        .where(Campaign.company_id == user.company_id, Campaign.archived.is_(False),
                               Tunnel.kind == "sales", TunnelEvent.created_at >= since,
                               ((TunnelEvent.kind == "page_view") &
                                (TunnelEvent.page_id == Tunnel.entry_page_id)) |
                               (TunnelEvent.kind == "goal_click"))
                        .group_by(TunnelEvent.kind)).all()
    measured = dict(events)
    visits = measured.get("page_view", 0)
    goals = measured.get("goal_click", 0)
    return {"active": statuses.get("active", 0), "drafts": statuses.get("draft", 0),
            "visits": visits, "goals": goals,
            "conversion": round(goals / visits * 100, 1) if visits else 0,
            "period_days": 30}


@router.post("/api/sales-funnels", status_code=201)
def create_sales_funnel(data: SalesTunnelCreate, db: Session = Depends(get_db), user: User = Depends(write_user)):
    if not settings.openai_api_key:
        raise HTTPException(503, "Configurez Luna pour créer un tunnel avec l'IA.")
    identity = brand_identity(user.company)
    try:
        landing_html, landing_manifest = generate_step("landing", data, identity)
        offer_html, offer_manifest = generate_step("offer", data, identity)
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    campaign = Campaign(company_id=user.company_id, creator_id=user.id, name=data.name,
                        objective=data.offer)
    db.add(campaign)
    db.flush()
    tunnel = Tunnel(campaign_id=campaign.id, name=data.name, slug=slugify(data.name),
                    status="draft", kind="sales", brief=data.model_dump(), identity=identity,
                    goal_url=data.goal_url, goal_label=data.goal_label)
    db.add(tunnel)
    db.flush()
    landing = Page(tunnel_id=tunnel.id, name="Découverte", role="landing", position=0,
                   html=landing_html, manifest=landing_manifest)
    offer = Page(tunnel_id=tunnel.id, name="L'offre", role="offer", position=1,
                 html=offer_html, manifest=offer_manifest)
    db.add_all([landing, offer])
    db.flush()
    landing.next_page_id = offer.id
    tunnel.entry_page_id = landing.id
    db.commit()
    db.refresh(tunnel)
    return tunnel_payload(tunnel)


@router.get("/api/sales-funnels/{tunnel_id}")
def get_sales_funnel(tunnel_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return tunnel_payload(owned_tunnel(tunnel_id, db, user))


@router.patch("/api/sales-funnels/{tunnel_id}/destination")
def update_sales_destination(tunnel_id: str, data: SalesDestinationUpdate,
                             db: Session = Depends(get_db), user: User = Depends(write_user)):
    tunnel = owned_tunnel(tunnel_id, db, user)
    tunnel.goal_url = data.goal_url
    db.commit()
    return tunnel_payload(tunnel)


@router.post("/api/sales-funnels/{tunnel_id}/pages/{page_id}/refine")
def refine_sales_page(tunnel_id: str, page_id: str, data: SalesPageRefine,
                      db: Session = Depends(get_db), user: User = Depends(write_user)):
    if not settings.openai_api_key:
        raise HTTPException(503, "Configurez Luna pour retoucher cette page.")
    tunnel = owned_tunnel(tunnel_id, db, user)
    page = next((item for item in tunnel.pages if item.id == page_id), None)
    if not page:
        raise HTTPException(404, "Page introuvable")
    current = page.draft_html or page.html
    try:
        result = revise_page(
            current, data.instruction, tunnel.identity or {},
            selection={"view": page.role, "page_role": page.role, "element_ids": [], "label": page.name},
            brief=tunnel.brief or {}, stats={"visits": page.visits, "conversions": page.conversions},
            api_key=settings.openai_api_key, model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds, page_instructions=SALES_PAGE_INSTRUCTIONS,
        )
        if not result["html"].strip():
            return {"message": result["message"], "changed": False, "tunnel": tunnel_payload(tunnel)}
        html, manifest = prepare_page(merge_page_region(current, result["html"], result["region"]), require_form=False)
        validate_sales_page(html, page.role)
        if manifest:
            raise ValueError("La page doit garder son bouton d'action et ne pas contenir de formulaire.")
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if same_document(html, current):
        return {"message": "La page est déjà conforme à cette demande.", "changed": False,
                "tunnel": tunnel_payload(tunnel)}
    page.draft_html = html
    db.commit()
    return {"message": result["message"], "changed": True, "tunnel": tunnel_payload(tunnel)}


@router.get("/api/sales-funnels/{tunnel_id}/pages/{page_id}/versions")
def sales_page_versions(tunnel_id: str, page_id: str, db: Session = Depends(get_db),
                        user: User = Depends(current_user)):
    tunnel = owned_tunnel(tunnel_id, db, user)
    if not any(page.id == page_id for page in tunnel.pages):
        raise HTTPException(404, "Page introuvable")
    versions = db.scalars(select(PageVersion).where(PageVersion.page_id == page_id)
                          .order_by(desc(PageVersion.created_at)).limit(30)).all()
    return [{"id": version.id, "created_at": version.created_at.isoformat()} for version in versions]


@router.post("/api/sales-funnels/{tunnel_id}/pages/{page_id}/versions/{version_id}/restore")
def restore_sales_page(tunnel_id: str, page_id: str, version_id: str,
                       db: Session = Depends(get_db), user: User = Depends(write_user)):
    tunnel = owned_tunnel(tunnel_id, db, user)
    page = next((item for item in tunnel.pages if item.id == page_id), None)
    version = db.get(PageVersion, version_id)
    if not page or not version or version.page_id != page.id:
        raise HTTPException(404, "Version introuvable")
    page.draft_html = version.html
    db.commit()
    return tunnel_payload(tunnel)


@router.post("/api/sales-funnels/{tunnel_id}/pages/{page_id}/discard")
def discard_sales_page(tunnel_id: str, page_id: str, db: Session = Depends(get_db),
                       user: User = Depends(write_user)):
    tunnel = owned_tunnel(tunnel_id, db, user)
    page = next((item for item in tunnel.pages if item.id == page_id), None)
    if not page:
        raise HTTPException(404, "Page introuvable")
    page.draft_html = None
    db.commit()
    return tunnel_payload(tunnel)


@router.post("/api/sales-funnels/{tunnel_id}/publish")
def publish_sales_funnel(tunnel_id: str, db: Session = Depends(get_db), user: User = Depends(write_user)):
    tunnel = owned_tunnel(tunnel_id, db, user)
    for page in tunnel.pages:
        if page.draft_html:
            db.add(PageVersion(page_id=page.id, html=page.html))
            page.html = page.draft_html
            page.draft_html = None
    tunnel.status = "active"
    db.commit()
    return tunnel_payload(tunnel)


@router.post("/api/sales-funnels/{tunnel_id}/pause")
def pause_sales_funnel(tunnel_id: str, db: Session = Depends(get_db), user: User = Depends(write_user)):
    tunnel = owned_tunnel(tunnel_id, db, user)
    tunnel.status = "draft"
    db.commit()
    return tunnel_payload(tunnel)


@router.get("/api/sales-funnels/{tunnel_id}/export.zip")
def export_sales_funnel(tunnel_id: str, db: Session = Depends(get_db),
                        user: User = Depends(current_user)):
    tunnel = owned_tunnel(tunnel_id, db, user)
    if tunnel.status != "active":
        raise HTTPException(422, "Publiez le tunnel avant de l'exporter.")
    pages = sorted(tunnel.pages, key=lambda page: page.position)
    if len(pages) != 2:
        raise HTTPException(422, "Ce parcours ne peut pas encore être exporté.")
    destination = json.dumps(tunnel.goal_url).replace("<", "\\u003c")
    script = ("<script>document.addEventListener('click',function(event){"
              "if(event.target.closest('[data-sillage-next]')){location.href='offre.html'}"
              f"if(event.target.closest('[data-sillage-goal]')){{location.href={destination}}}"
              "})</script>")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for page, filename in zip(pages, ("index.html", "offre.html"), strict=True):
            output.writestr(filename, page.html.replace("</body>", script + "</body>", 1))
        output.writestr("LISEZ-MOI.txt", "Ce dossier contient une copie HTML du tunnel publié.\n"
                        "Ouvrez index.html pour commencer. Le bouton final mène à l'adresse externe configurée.\n"
                        "Cette copie ne transmet aucune statistique à Sillage et ne suit pas les réservations ou ventes externes.\n")
    return Response(archive.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{tunnel.slug}.zip"'})


@router.get("/api/sales-funnels/{tunnel_id}/stats")
def sales_stats(tunnel_id: str, days: int = Query(default=30, ge=1, le=90),
                db: Session = Depends(get_db), user: User = Depends(current_user)):
    tunnel = owned_tunnel(tunnel_id, db, user)
    today = datetime.now(timezone.utc).date()
    since = datetime.combine(today - timedelta(days=days - 1), datetime.min.time(), timezone.utc)
    rows = db.execute(select(TunnelEvent.page_id, TunnelEvent.kind, func.count(TunnelEvent.id))
                      .where(TunnelEvent.tunnel_id == tunnel.id, TunnelEvent.created_at >= since)
                      .group_by(TunnelEvent.page_id, TunnelEvent.kind)).all()
    counts = {(page_id, kind): count for page_id, kind, count in rows}
    sources = db.execute(select(TunnelEvent.source, TunnelEvent.kind, func.count(TunnelEvent.id))
                         .where(TunnelEvent.tunnel_id == tunnel.id, TunnelEvent.created_at >= since,
                                ((TunnelEvent.page_id == tunnel.entry_page_id) & (TunnelEvent.kind == "page_view")) |
                                (TunnelEvent.kind == "goal_click"))
                         .group_by(TunnelEvent.source, TunnelEvent.kind)).all()
    by_source: dict[str, dict] = {}
    for source, kind, count in sources:
        item = by_source.setdefault(source, {"source": source, "visits": 0, "goals": 0})
        item["visits" if kind == "page_view" else "goals"] = count
    pages = sorted(tunnel.pages, key=lambda page: page.position)
    entry_visits = counts.get((tunnel.entry_page_id, "page_view"), 0)
    goals = sum(count for (page_id, kind), count in counts.items() if kind == "goal_click")
    daily_rows = db.execute(select(func.date(TunnelEvent.created_at), TunnelEvent.kind, func.count(TunnelEvent.id))
                            .where(TunnelEvent.tunnel_id == tunnel.id, TunnelEvent.created_at >= since,
                                   ((TunnelEvent.page_id == tunnel.entry_page_id) & (TunnelEvent.kind == "page_view")) |
                                   (TunnelEvent.kind == "goal_click"))
                            .group_by(func.date(TunnelEvent.created_at), TunnelEvent.kind)).all()
    daily_counts = {(day.isoformat() if hasattr(day, "isoformat") else day, kind): count
                    for day, kind, count in daily_rows}
    daily = [{"date": (today - timedelta(days=offset)).isoformat(),
              "visits": daily_counts.get(((today - timedelta(days=offset)).isoformat(), "page_view"), 0),
              "goals": daily_counts.get(((today - timedelta(days=offset)).isoformat(), "goal_click"), 0)}
             for offset in range(days - 1, -1, -1)]
    return {"period_days": days, "visits": entry_visits, "goals": goals,
            "conversion": round(goals / entry_visits * 100, 1) if entry_visits else 0,
            "pages": [{"id": page.id, "name": page.name, "visits": counts.get((page.id, "page_view"), 0),
                       "actions": counts.get((page.id, "step_click"), 0) + counts.get((page.id, "goal_click"), 0),
                       "continuation": round(counts.get((page.id, "step_click"), 0) / counts.get((page.id, "page_view"), 1) * 100, 1)
                       if page.next_page_id and counts.get((page.id, "page_view"), 0) else None}
                      for page in pages], "sources": list(by_source.values()), "daily": daily}


def live_tunnel(slug: str, db: Session) -> Tunnel:
    tunnel = db.scalar(select(Tunnel).where(Tunnel.slug == slug, Tunnel.kind == "sales", Tunnel.status == "active"))
    if not tunnel or tunnel.campaign.archived:
        raise HTTPException(404, "Tunnel indisponible")
    return tunnel


def journey(request: Request, tunnel: Tunnel) -> dict | None:
    try:
        token = request.cookies.get("sillage_sales_journey", "")
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return payload if payload.get("tunnel") == tunnel.id else None
    except jwt.PyJWTError:
        return None


def set_journey(response: Response, request: Request, payload: dict) -> None:
    token = jwt.encode({**payload, "exp": datetime.now(timezone.utc) + timedelta(hours=24)},
                       settings.secret_key, algorithm="HS256")
    response.set_cookie("sillage_sales_journey", token, max_age=86400, httponly=True,
                        secure=request.url.scheme == "https", samesite="lax", path="/api/public/sales")


def record_event(db: Session, tunnel: Tunnel, page: Page, sid: str, kind: str, source: str) -> bool:
    values = {"id": str(uuid4()), "tunnel_id": tunnel.id, "page_id": page.id,
              "session_id": sid, "event_key": f"{sid}:{page.id}:{kind}", "kind": kind, "source": source}
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        statement = pg_insert(TunnelEvent).values(**values).on_conflict_do_nothing(index_elements=["event_key"])
    elif dialect == "sqlite":
        statement = sqlite_insert(TunnelEvent).values(**values).on_conflict_do_nothing(index_elements=["event_key"])
    else:
        raise RuntimeError("Dialecte de mesure non pris en charge")
    inserted = db.execute(statement).rowcount > 0
    if inserted:
        if kind == "page_view":
            page.visits += 1
        elif kind in {"step_click", "goal_click"}:
            page.conversions += 1
    return inserted


def public_page(page: Page) -> dict:
    return {"page_id": page.id, "name": page.name, "role": page.role,
            "next_page_id": page.next_page_id, "html": render_page(page.html, "")}


@router.post("/api/public/sales/{slug}/visit")
def visit_sales_funnel(slug: str, data: SalesJourneyStart, request: Request, response: Response,
                       db: Session = Depends(get_db)):
    rate_limit("sales-journey", client_ip(request), limit=JOURNEY_CALLS, window_seconds=JOURNEY_WINDOW)
    tunnel = live_tunnel(slug, db)
    previous = journey(request, tunnel)
    sid = previous.get("sid") if previous else str(uuid4())
    source = previous.get("source") if previous else data.source.strip()[:80] or "Lien direct"
    page = db.get(Page, previous.get("page")) if previous else None
    if not page or page.tunnel_id != tunnel.id:
        page = db.get(Page, tunnel.entry_page_id)
    record_event(db, tunnel, page, sid, "page_view", source)
    db.commit()
    set_journey(response, request, {"tunnel": tunnel.id, "sid": sid, "page": page.id, "source": source})
    return public_page(page)


@router.post("/api/public/sales/{slug}/advance")
def advance_sales_funnel(slug: str, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit("sales-journey", client_ip(request), limit=JOURNEY_CALLS, window_seconds=JOURNEY_WINDOW)
    tunnel = live_tunnel(slug, db)
    current = journey(request, tunnel)
    page = db.get(Page, current.get("page")) if current else None
    if not page or page.tunnel_id != tunnel.id or not page.next_page_id or not current.get("sid"):
        raise HTTPException(403, "Étape inaccessible")
    next_page = db.get(Page, page.next_page_id)
    if not next_page or next_page.tunnel_id != tunnel.id:
        raise HTTPException(422, "Parcours invalide")
    record_event(db, tunnel, page, current["sid"], "step_click", current.get("source") or "Lien direct")
    record_event(db, tunnel, next_page, current["sid"], "page_view", current.get("source") or "Lien direct")
    db.commit()
    set_journey(response, request, {**current, "page": next_page.id})
    return public_page(next_page)


@router.post("/api/public/sales/{slug}/goal")
def sales_goal(slug: str, request: Request, db: Session = Depends(get_db)):
    rate_limit("sales-journey", client_ip(request), limit=JOURNEY_CALLS, window_seconds=JOURNEY_WINDOW)
    tunnel = live_tunnel(slug, db)
    current = journey(request, tunnel)
    page = db.get(Page, current.get("page")) if current else None
    if not page or page.tunnel_id != tunnel.id or page.next_page_id or not tunnel.goal_url or not current.get("sid"):
        raise HTTPException(403, "Action inaccessible")
    record_event(db, tunnel, page, current["sid"], "goal_click", current.get("source") or "Lien direct")
    db.commit()
    return {"url": tunnel.goal_url}
