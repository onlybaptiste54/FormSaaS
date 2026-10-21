import csv
import io
import json
import logging
import re
import unicodedata
from html import escape
from uuid import uuid4
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone

import httpx
import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import Text, cast, desc, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, get_db, initialize_schema
from .brand_site import SiteError, read_site
from .luna import LunaAPIError, analyze_brand, analyze_site_brand, default_content, default_design, generate_campaign, generate_page, merge_page_region, revise_page, slugify, stream_page_revision
from .luna_ops import contrast_ratio
from .models import Campaign, Company, Form, FormResponse, FormVersion, Page, Template, Tunnel, User, initial_tunnel_id, thanks_page_id, uid
from .page_document import blank_form_html, legacy_to_html, prepare_page, render_page
from .schemas import BrandAnalyzeRequest, CampaignCreate, CampaignUpdate, CompanyUpdate, DraftUpdate, FormCreate, FormUpdate, LoginIn, LunaRefineRequest, PublicPageAdvance, PublicPageVisit, SubmitResponse, SiteBrandRequest, TemplateUse, TunnelPageCreate, TunnelPageUpdate
from .security import create_token, current_user, verify_password
from .seed import seed
from .template_catalog import CURATED_TEMPLATES, campaign_fields, curated_template, template_kind, template_payload


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Les mesures de Luna (duree, tentatives, tokens) doivent etre visibles.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    initialize_schema()
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="Sillage API", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


EDITABLE_KEYS = ("name", "description", "fields", "design", "content", "thank_you")

# Nombre de versions conservees par formulaire.
VERSION_LIMIT = 30


def thank_you_settings(form: Form) -> dict:
    page = next((item for item in form.pages if item.role == "thanks"), None)
    return (page.settings if page and page.settings is not None else form.thank_you) or {}


def published_state(f: Form) -> dict:
    """Etat en ligne du formulaire : ce que voit un visiteur."""
    return {
        "name": f.name,
        "description": f.description,
        "fields": f.fields,
        "design": f.design or default_design(),
        "content": f.content or default_content(f.kind),
        "thank_you": thank_you_settings(f),
    }


def editing_state(f: Form) -> dict:
    """Etat en cours d'edition : le brouillon s'il existe, sinon le publie."""
    return {**published_state(f), **(f.draft or {})}


def form_page(form: Form, role: str = "form") -> Page:
    return next(page for page in form.pages if page.role == role)


def converted_html(form: Form, state: dict, *, role: str = "form") -> tuple[str, list[dict]]:
    company = form.campaign.company
    identity = {key: getattr(company, key) for key in ("name", "legal_name", "address", "dpo_email", "logo")}
    return prepare_page(legacy_to_html({**state, "kind": form.kind}, identity, role=role), require_form=role == "form")


def create_form_pages(db: Session, form: Form, initial_html: tuple[str, list[dict]] | None = None) -> None:
    """Initialise les deux documents des nouveaux formulaires, dans la transaction courante."""
    db.flush()
    tunnel_id = initial_tunnel_id(form.id)
    tunnel = Tunnel(id=tunnel_id, campaign_id=form.campaign_id, name=form.name,
                    slug=form.slug, status=form.status)
    db.add(tunnel)
    db.flush()
    state = published_state(form)
    html, manifest = initial_html if initial_html is not None else converted_html(form, state)
    thanks_html, _ = converted_html(form, state, role="thanks")
    thanks = Page(id=thanks_page_id(form.id), form=form, tunnel_id=tunnel_id,
                  name="Page de remerciement", role="thanks", position=1, html=thanks_html,
                  settings=state["thank_you"])
    db.add(thanks)
    db.flush()
    db.add(Page(id=form.id, form=form, tunnel_id=tunnel_id, name=form.name, slug=form.slug, role="form", position=0,
                next_page_id=thanks.id, html=html, manifest=manifest, visits=form.visits))
    # La page doit exister en base avant que le tunnel ne pointe dessus.
    db.flush()
    tunnel.entry_page_id = form.id
    form.thank_you = {}


def copy_form_pages(db: Session, source: Form, target: Form) -> None:
    """Duplicate the published tunnel while resetting its measurements."""
    db.flush()
    tunnel_id = initial_tunnel_id(target.id)
    tunnel = Tunnel(id=tunnel_id, campaign_id=target.campaign_id, name=target.name,
                    slug=target.slug, status=target.status)
    db.add(tunnel)
    db.flush()
    source_tunnel = db.get(Tunnel, initial_tunnel_id(source.id))
    source_pages = sorted(source_tunnel.pages, key=lambda item: item.position)
    mapped = {page.id: target.id if page.id == source.id else thanks_page_id(target.id)
              if page.id == thanks_page_id(source.id) else uid() for page in source_pages}
    for old in source_pages:
        html, manifest = prepare_page(old.html, require_form=old.role == "form")
        db.add(Page(id=mapped[old.id], form=target if old.form_id == source.id else None,
                    tunnel_id=tunnel_id, name=target.name if old.id == source.id else old.name,
                    slug=target.slug if old.id == source.id else None,
                    role=old.role, position=old.position, html=html, manifest=manifest,
                    settings=(old.settings or source.thank_you) if old.role == "thanks" else {}))
    db.flush()
    for old in source_pages:
        if old.next_page_id:
            db.get(Page, mapped[old.id]).next_page_id = mapped[old.next_page_id]
    tunnel.entry_page_id = mapped[source_tunnel.entry_page_id]
    target.thank_you = {}


def consent_text(form: Form) -> str:
    label = next(
        (str(field.get("label", "")).strip() for field in form.fields
         if field.get("type") == "consent" and str(field.get("label", "")).strip()),
        "",
    )
    return label or "J'accepte le traitement de mes données pour répondre à ma demande."


def field_warnings(db: Session, form: Form, page: Page) -> list[str]:
    """Signale les anciens noms encore présents dans des réponses conservées."""
    if page.draft_manifest is None:
        return []
    current = {field["name"] for field in page.draft_manifest}
    warnings = []
    for field in page.manifest:
        name = field["name"]
        if name in current:
            continue
        if db.get_bind().dialect.name == "postgresql":
            present = cast(FormResponse.answers, JSONB).has_key(name)
        else:
            present = func.json_type(FormResponse.answers, f'$."{name}"').is_not(None)
        count = db.scalar(select(func.count(FormResponse.id)).where(FormResponse.form_id == form.id, present)) or 0
        if count:
            warnings.append(f"{count} réponses étaient rattachées à « {name} » ; elles restent consultables dans l'historique.")
    return warnings


def record_version(db: Session, form: Form, snapshot: dict, *, source: str, instruction: str = "", message: str = "", screenshot_data_url: str | None = None, images: list[str] | None = None) -> FormVersion:
    version = FormVersion(form_id=form.id, snapshot=snapshot, source=source, instruction=instruction,
                          message=message, screenshot_data_url=screenshot_data_url, images=images or [])
    db.add(version)
    db.flush()
    extra = db.scalars(
        select(FormVersion).where(FormVersion.form_id == form.id).order_by(desc(FormVersion.created_at)).offset(VERSION_LIMIT)
    ).all()
    for old in extra:
        db.delete(old)
    return version


def version_json(version: FormVersion):
    return {
        "id": version.id,
        "source": version.source,
        "instruction": version.instruction,
        "message": version.message,
        "created_at": version.created_at.isoformat(),
        "screenshot_data_url": getattr(version, "screenshot_data_url", None),
        "images": getattr(version, "images", None) or [],
        "restored_to_version_id": (version.snapshot or {}).get("_restored_to_version_id"),
        "page_id": (version.snapshot or {}).get("page_id"),
    }


def form_health(f: Form, company: Company) -> dict:
    """Score de qualite reellement calcule, avec les points a corriger."""
    state = editing_state(f)
    business = [field for field in state["fields"] if field.get("type") != "consent"]
    style = (state["design"] or {}).get("style") or {}
    required = [field for field in business if field.get("required")]
    checks = [
        {"label": "Formulaire court", "ok": len(business) <= 5, "hint": "Retirez un champ : cinq suffisent."},
        {"label": "Peu de champs obligatoires", "ok": len(required) <= 3, "hint": "Rendez un champ facultatif pour limiter les abandons."},
        {"label": "Consentement conforme", "ok": any(field.get("type") == "consent" for field in state["fields"]), "hint": "Le consentement RGPD doit rester présent."},
        {"label": "Texte lisible", "ok": not (style.get("ink") and style.get("surface")) or contrast_ratio(style["ink"], style["surface"]) >= 4.5, "hint": "Augmentez le contraste entre le texte et la carte."},
        {"label": "Bouton lisible", "ok": not (style.get("accent_ink") and style.get("accent")) or contrast_ratio(style["accent_ink"], style["accent"]) >= 4.5, "hint": "Augmentez le contraste du bouton."},
        {"label": "Contact RGPD renseigné", "ok": bool(company.dpo_email), "hint": "Ajoutez l'email DPO dans les paramètres."},
        {"label": "Remerciement personnalisé", "ok": bool((state["thank_you"] or {}).get("message")), "hint": "Écrivez un message de remerciement."},
    ]
    score = round(sum(check["ok"] for check in checks) / len(checks) * 100)
    return {"score": score, "checks": checks}


def count_responses(db: Session, form_id: str) -> int:
    return db.scalar(select(func.count(FormResponse.id)).where(FormResponse.form_id == form_id)) or 0


def form_json(db: Session, f: Form):
    responses = count_responses(db, f.id)
    page = form_page(f)
    thanks = form_page(f, "thanks")
    legal = consent_text(f)
    return {
        "id": f.id,
        "campaign_id": f.campaign_id,
        "campaign_name": f.campaign.name,
        "name": f.name,
        "slug": f.slug,
        "description": f.description,
        "kind": f.kind,
        "status": f.status,
        "visibility": f.visibility,
        "fields": f.fields,
        "design": f.design or default_design(),
        "content": f.content or default_content(f.kind),
        "thank_you": thank_you_settings(f),
        "draft": f.draft,
        "html": render_page(page.html, legal),
        "draft_html": render_page(page.draft_html, legal) if page.draft_html else None,
        "thanks_html": render_page(thanks.draft_html or thanks.html, legal, {}),
        "manifest": page.manifest,
        "field_warnings": field_warnings(db, f, page),
        "health": form_health(f, f.campaign.company),
        "visits": f.visits,
        "responses": responses,
        "conversion": round((responses / f.visits * 100) if f.visits else 0, 1),
        "archived": f.archived,
        "created_at": f.created_at.isoformat(),
        "updated_at": f.updated_at.isoformat(),
    }


def campaign_summaries(db: Session, campaigns: list[Campaign]) -> dict[str, dict]:
    """Bilan de chaque campagne, compte en SQL : jamais en chargeant les reponses."""
    ids = [c.id for c in campaigns]
    empty = {"forms": 0, "active": 0, "visits": 0, "responses": 0, "last_activity": None}
    if not ids:
        return {}
    summaries = {campaign_id: dict(empty) for campaign_id in ids}
    forms = db.execute(
        select(Form.campaign_id, func.count(Form.id), func.coalesce(func.sum(Form.visits), 0), func.max(Form.updated_at))
        .where(Form.campaign_id.in_(ids), Form.archived.is_(False))
        .group_by(Form.campaign_id)
    ).all()
    for campaign_id, total, visits, updated in forms:
        summaries[campaign_id].update({"forms": total, "visits": int(visits or 0), "last_activity": updated})
    active = db.execute(
        select(Form.campaign_id, func.count(Form.id))
        .where(Form.campaign_id.in_(ids), Form.archived.is_(False), Form.status == "active")
        .group_by(Form.campaign_id)
    ).all()
    for campaign_id, total in active:
        summaries[campaign_id]["active"] = total
    responses = db.execute(
        select(Form.campaign_id, func.count(FormResponse.id), func.max(FormResponse.created_at))
        .join(FormResponse, FormResponse.form_id == Form.id)
        .where(Form.campaign_id.in_(ids))
        .group_by(Form.campaign_id)
    ).all()
    for campaign_id, total, last in responses:
        summary = summaries[campaign_id]
        summary["responses"] = total
        if last and (not summary["last_activity"] or last > summary["last_activity"]):
            summary["last_activity"] = last
    return summaries


def campaign_json(c: Campaign, summary: dict):
    visits = summary["visits"]
    responses = summary["responses"]
    last = summary["last_activity"] or c.updated_at
    return {
        "id": c.id,
        "name": c.name,
        "client": c.client,
        "objective": c.objective,
        "starts_on": c.starts_on.isoformat() if c.starts_on else None,
        "ends_on": c.ends_on.isoformat() if c.ends_on else None,
        "forms": summary["forms"],
        "active": summary["active"],
        "visits": visits,
        "responses": responses,
        "conversion": round((responses / visits * 100) if visits else 0, 1),
        "last_activity": last.isoformat(),
        "archived": c.archived,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


def one_campaign_json(db: Session, c: Campaign):
    return campaign_json(c, campaign_summaries(db, [c])[c.id])


def template_preview(payload: dict, company: Company) -> dict:
    """Même document pour les vignettes et le formulaire créé depuis un modèle."""
    fields = campaign_fields(payload["fields"], company.name)
    state = {**payload, "fields": fields}
    identity = {key: getattr(company, key) for key in ("name", "legal_name", "address", "dpo_email", "logo")}
    html, _ = prepare_page(legacy_to_html(state, identity), require_form=True)
    return {**payload, "html": render_page(html, fields[-1]["label"])}


def saved_template_json(template: Template, company: Company | None = None):
    payload = {
        "id": template.id,
        "key": template.source_key,
        "name": template.name,
        "category": template.category,
        "description": template.description,
        "fields": template.fields,
        "field_count": len(template.fields),
        "design": template.design or default_design(),
        "content": default_content(template_kind(template.category)),
        "thank_you": template.thank_you,
        "uses": template.uses,
        "created_at": template.created_at.isoformat(),
        "updated_at": template.updated_at.isoformat(),
    }
    return template_preview(payload, company) if company else payload


def unique_slug(db: Session, name: str) -> str:
    """Deux campagnes peuvent avoir un formulaire du meme nom : le lien doit rester unique."""
    base = slugify(name)
    candidate = base
    suffix = 2
    while db.scalar(select(Form.id).where(Form.slug == candidate)):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def form_from_template(db: Session, template: dict, user: User, campaign: Campaign) -> Form:
    kind = template_kind(template.get("category", "Contact"))
    return Form(
        campaign_id=campaign.id,
        creator_id=user.id,
        identity=luna_identity(user.company),
        name=template["name"],
        slug=unique_slug(db, template["name"]),
        description=template["description"],
        kind=kind,
        status="draft",
        visibility="private",
        fields=campaign_fields(template["fields"], user.company.name),
        design=template.get("design") or default_design(),
        content=default_content(kind),
        thank_you=template.get("thank_you") or template_payload(template)["thank_you"],
    )


def luna_history(form: Form) -> list[dict]:
    """Derniers echanges, pour que Luna se souvienne de la conversation."""
    turns = []
    for version in [item for item in form.versions if item.source == "luna"][-6:]:
        if version.instruction:
            images = [image for image in [getattr(version, "screenshot_data_url", None), *(getattr(version, "images", None) or [])] if image]
            turns.append({"role": "user", "text": version.instruction, "images": images})
        if version.message:
            turns.append({"role": "luna", "text": version.message})
    return turns


def luna_identity(company: Company) -> dict:
    """Ce que Luna sait de la marque : rien de personnel, rien de juridique."""
    return {
        "name": company.name,
        "sector": company.sector,
        "tone": company.tone,
        "primary_color": company.primary_color,
        "accent_color": company.accent_color,
        "brand": company.brand or {},
    }


def page_identity(form: Form) -> dict:
    """L'identite que cette page applique, figee a sa creation.

    NULL signale un formulaire cree avant que l'identite ne soit figee : il
    retombe sur celle du compte. Un dictionnaire vide est un choix explicite de
    n'appliquer aucune identite, et doit le rester.
    """
    if form.identity is not None:
        return form.identity
    return luna_identity(form.campaign.company)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Email ou mot de passe incorrect")
    return {"access_token": create_token(user), "token_type": "bearer"}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    c = user.company
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role, "company": {"id": c.id, "name": c.name, "legal_name": c.legal_name, "sector": c.sector, "siret": c.siret, "address": c.address, "primary_color": c.primary_color, "accent_color": c.accent_color, "tone": c.tone, "dpo_email": c.dpo_email, "logo": c.logo, "brand": c.brand or {}}}


@app.get("/api/luna/status")
def luna_status(_: User = Depends(current_user)):
    configured = bool(settings.openai_api_key)
    return {
        "configured": configured,
        "provider": "openai" if configured else "local",
        "model": settings.openai_model if configured else None,
    }


@app.patch("/api/company")
def update_company(data: CompanyUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(user.company, key, value)
    db.commit()
    return me(user)


@app.post("/api/company/brand/analyze")
def analyze_company_brand(data: BrandAnalyzeRequest, user: User = Depends(current_user)):
    """Propose un profil de marque : rien n'est enregistre tant qu'il n'est pas valide."""
    try:
        return analyze_brand(
            data.images,
            luna_identity(user.company),
            notes=data.notes,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
        )
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/brand/from-site")
def brand_from_site(data: SiteBrandRequest, user: User = Depends(current_user)):
    """Propose une charte lue sur un site public : rien n'est enregistre.

    La reponse rend aussi les elements releves, pour que l'interface montre sur
    quoi la proposition s'appuie et laisse corriger plutot que deviner.
    """
    try:
        facts = read_site(data.url)
    except SiteError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Ce site n'a pas répondu.") from exc
    try:
        profile = analyze_site_brand(
            facts,
            luna_identity(user.company),
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
        )
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"profile": profile, "evidence": facts}


@app.get("/api/stats")
def stats(db: Session = Depends(get_db), user: User = Depends(current_user)):
    forms = db.scalars(
        select(Form).join(Campaign, Form.campaign_id == Campaign.id)
        .where(Campaign.company_id == user.company_id, Campaign.archived.is_(False), Form.archived.is_(False))
    ).all()
    ids = [f.id for f in forms]
    campaigns = db.scalar(select(func.count(Campaign.id)).where(Campaign.company_id == user.company_id, Campaign.archived.is_(False))) or 0
    total = db.scalar(select(func.count(FormResponse.id)).where(FormResponse.form_id.in_(ids))) if ids else 0
    since = datetime.now(timezone.utc) - timedelta(days=7)
    week = db.scalar(select(func.count(FormResponse.id)).where(FormResponse.form_id.in_(ids), FormResponse.created_at >= since)) if ids else 0
    daily = []
    for offset in range(6, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=offset)).date()
        count = db.scalar(select(func.count(FormResponse.id)).where(FormResponse.form_id.in_(ids), func.date(FormResponse.created_at) == day)) if ids else 0
        daily.append({"date": day.isoformat(), "count": count or 0})
    visits = sum(f.visits for f in forms)
    sources = db.execute(select(FormResponse.source, func.count(FormResponse.id)).where(FormResponse.form_id.in_(ids)).group_by(FormResponse.source).order_by(desc(func.count(FormResponse.id)))) if ids else []
    recent = db.scalars(select(FormResponse).where(FormResponse.form_id.in_(ids)).order_by(desc(FormResponse.created_at)).limit(5)).all() if ids else []
    return {
        "campaigns": campaigns,
        "forms": len(forms),
        "active": sum(f.status == "active" for f in forms),
        "drafts": sum(f.status != "active" for f in forms),
        "responses": total or 0,
        "week_responses": week or 0,
        "conversion": round((total / visits * 100) if visits else 0, 1),
        "daily": daily,
        "sources": [{"name": name, "count": count} for name, count in sources],
        "recent": [{"id": r.id, "form_id": r.form_id, "form": r.form.name, "campaign": r.form.campaign.name, "name": r.answers.get("name", "Réponse anonyme"), "source": r.source, "created_at": r.created_at.isoformat()} for r in recent],
    }


@app.get("/api/team")
def team(db: Session = Depends(get_db), user: User = Depends(current_user)):
    members = db.scalars(select(User).where(User.company_id == user.company_id).order_by(User.created_at)).all()
    return [{"id": m.id, "full_name": m.full_name, "email": m.email, "role": m.role} for m in members]


# --- Campagnes ---------------------------------------------------------------


def owned_campaign(campaign_id: str, db: Session, user: User) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.company_id != user.company_id:
        raise HTTPException(404, "Campagne introuvable")
    return campaign


@app.get("/api/campaigns")
def list_campaigns(archived: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaigns = db.scalars(select(Campaign).where(Campaign.company_id == user.company_id, Campaign.archived == archived).order_by(desc(Campaign.updated_at))).all()
    summaries = campaign_summaries(db, list(campaigns))
    return [campaign_json(c, summaries[c.id]) for c in campaigns]


@app.post("/api/campaigns", status_code=201)
def create_campaign(data: CampaignCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaign = Campaign(company_id=user.company_id, creator_id=user.id, **data.model_dump())
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return one_campaign_json(db, campaign)


@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return one_campaign_json(db, owned_campaign(campaign_id, db, user))


@app.patch("/api/campaigns/{campaign_id}")
def update_campaign(campaign_id: str, data: CampaignUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaign = owned_campaign(campaign_id, db, user)
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(campaign, key, value)
    db.commit()
    return one_campaign_json(db, campaign)


@app.get("/api/campaigns/{campaign_id}/stats")
def campaign_stats(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Bilan de la campagne : ce que chaque formulaire apporte, agrege en SQL."""
    campaign = owned_campaign(campaign_id, db, user)
    forms = db.scalars(select(Form).where(Form.campaign_id == campaign.id, Form.archived.is_(False)).order_by(Form.created_at)).all()
    ids = [f.id for f in forms]
    counts = dict(db.execute(select(FormResponse.form_id, func.count(FormResponse.id)).where(FormResponse.form_id.in_(ids)).group_by(FormResponse.form_id)).all()) if ids else {}
    visits = sum(f.visits for f in forms)
    responses = sum(counts.values())
    breakdown = [
        {
            "id": f.id,
            "name": f.name,
            "status": f.status,
            "visits": f.visits,
            "responses": counts.get(f.id, 0),
            "conversion": round((counts.get(f.id, 0) / f.visits * 100) if f.visits else 0, 1),
        }
        for f in forms
    ]
    daily = []
    for offset in range(6, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=offset)).date()
        count = db.scalar(select(func.count(FormResponse.id)).where(FormResponse.form_id.in_(ids), func.date(FormResponse.created_at) == day)) if ids else 0
        daily.append({"date": day.isoformat(), "count": count or 0})
    sources = db.execute(select(FormResponse.source, func.count(FormResponse.id)).where(FormResponse.form_id.in_(ids)).group_by(FormResponse.source).order_by(desc(func.count(FormResponse.id)))).all() if ids else []
    best = max(breakdown, key=lambda row: (row["responses"], row["conversion"]), default=None)
    return {
        "forms": len(forms),
        "active": sum(f.status == "active" for f in forms),
        "visits": visits,
        "responses": responses,
        "conversion": round((responses / visits * 100) if visits else 0, 1),
        "best": best if best and best["responses"] else None,
        "breakdown": breakdown,
        "daily": daily,
        "sources": [{"name": name, "count": count} for name, count in sources],
    }


# --- Formulaires -------------------------------------------------------------


def owned_form(form_id: str, db: Session, user: User) -> Form:
    form = db.get(Form, form_id)
    if not form or form.campaign.company_id != user.company_id:
        raise HTTPException(404, "Formulaire introuvable")
    return form


@app.get("/api/campaigns/{campaign_id}/forms")
def list_forms(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaign = owned_campaign(campaign_id, db, user)
    forms = db.scalars(select(Form).where(Form.campaign_id == campaign.id).order_by(desc(Form.updated_at))).all()
    return [form_json(db, f) for f in forms]


@app.post("/api/campaigns/{campaign_id}/forms", status_code=201)
def create_form(campaign_id: str, data: FormCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaign = owned_campaign(campaign_id, db, user)
    try:
        # Decocher la marque doit tout retirer : avant, le nom, le secteur, le ton
        # et les couleurs de l'entreprise partaient quand meme.
        identity = luna_identity(user.company) if data.use_brand else {}
        # Les anciennes colonnes restent disponibles pendant la migration, mais
        # une seule génération IA écrit désormais le document visible.
        generated = generate_campaign(
            data.prompt,
            identity,
            context=data.context,
            images=data.images,
            api_key="",
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
        )
        initial_html = None
        if settings.openai_api_key:
            page_result = generate_page(
                data.prompt, identity, form_name=data.name, description=data.description,
                context=data.context, website_url=data.website_url, images=data.images,
                api_key=settings.openai_api_key, model=settings.openai_model,
                timeout_seconds=settings.openai_timeout_seconds,
            )
            initial_html = prepare_page(page_result["html"], require_form=True)
            consent = next(field for field in generated["fields"] if field.get("type") == "consent")
            generated["fields"] = [*initial_html[1], consent]
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # Le nom et la description saisis par l'utilisateur priment sur ceux de Luna.
    if data.name.strip():
        generated["name"] = data.name.strip()
    if data.description.strip():
        generated["description"] = data.description.strip()
    generated["slug"] = unique_slug(db, generated["name"])
    form = Form(campaign_id=campaign.id, creator_id=user.id, identity=identity,
                brief={"prompt": data.prompt, "context": data.context, "website_url": data.website_url}, **generated)
    db.add(form)
    create_form_pages(db, form, initial_html)
    db.commit()
    db.refresh(form)
    return form_json(db, form)


@app.get("/api/forms/{form_id}")
def get_form(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return form_json(db, owned_form(form_id, db, user))


@app.patch("/api/forms/{form_id}")
def update_form(form_id: str, data: FormUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    changes = data.model_dump(exclude_none=True)
    legacy_thank_you = changes.pop("thank_you", None)
    previous = published_state(form)
    page = form_page(form)
    thanks = form_page(form, "thanks")
    update_legacy_form = bool({"name", "description", "fields", "design"} & changes.keys()) and page.html == converted_html(form, previous)[0]
    update_legacy_thanks = legacy_thank_you is not None and thanks.html == converted_html(form, previous, role="thanks")[0]
    for key, value in changes.items():
        setattr(form, key, value)
    if legacy_thank_you is not None:
        new_settings = legacy_thank_you
        thanks.settings = new_settings
        form.thank_you = {}
    if "name" in changes:
        page.name = form.name
        tunnel = db.get(Tunnel, initial_tunnel_id(form.id))
        if tunnel:
            tunnel.name = form.name
    if "status" in changes:
        tunnel = db.get(Tunnel, initial_tunnel_id(form.id))
        if tunnel:
            tunnel.status = form.status
    if update_legacy_form:
        page.html, page.manifest = converted_html(form, published_state(form))
    if update_legacy_thanks:
        thanks.html, thanks.manifest = converted_html(form, published_state(form), role="thanks")
    db.commit()
    return form_json(db, form)


def form_tunnel(db: Session, form: Form) -> Tunnel:
    tunnel = db.get(Tunnel, initial_tunnel_id(form.id))
    if not tunnel or tunnel.campaign_id != form.campaign_id:
        raise HTTPException(404, "Tunnel introuvable")
    return tunnel


def tunnel_json(tunnel: Tunnel, form: Form) -> dict:
    pages = sorted(tunnel.pages, key=lambda item: (item.position, item.created_at, item.id))
    roles = {"landing": "Page d’accueil", "form": "Formulaire", "thanks": "Remerciement", "step": "Étape", "custom": "Page"}
    return {
        "id": tunnel.id, "name": tunnel.name, "status": tunnel.status,
        "entry_page_id": tunnel.entry_page_id,
        "pages": [{
            "id": page.id, "role": page.role, "position": page.position,
            "name": page.name or (page.slug.replace("-", " ").capitalize() if page.slug else roles.get(page.role, "Page")),
            "slug": page.slug, "next_page_id": page.next_page_id,
            "settings": page.settings or {},
            "html": render_page(page.draft_html or page.html, consent_text(form)),
            "visits": page.visits, "conversions": page.conversions,
        } for page in pages],
    }


def unique_page_slug(db: Session, name: str, *, exclude_page_id: str | None = None) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:70] or "etape"
    candidate = base
    suffix = 2
    while True:
        query = select(Page.id).where(Page.slug == candidate)
        if exclude_page_id:
            query = query.where(Page.id != exclude_page_id)
        if not db.scalar(query):
            return candidate
        tail = f"-{suffix}"
        candidate = f"{base[:70-len(tail)]}{tail}"
        suffix += 1


@app.get("/api/forms/{form_id}/tunnel")
def get_form_tunnel(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    return tunnel_json(form_tunnel(db, form), form)


@app.post("/api/forms/{form_id}/tunnel/pages", status_code=201)
def create_tunnel_page(form_id: str, data: TunnelPageCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    tunnel = form_tunnel(db, form)
    pages = sorted(tunnel.pages, key=lambda item: item.position)
    if len(pages) >= 20:
        raise HTTPException(422, "Le tunnel est limité à 20 pages")
    template = None
    if data.template_page_id:
        template = next((item for item in pages if item.id == data.template_page_id and item.role == data.role), None)
        if not template:
            raise HTTPException(422, "Le modèle doit être une page du même type dans ce tunnel")
    name = data.name.strip() or ("Page de présentation" if data.role == "landing" else "Nouvelle collecte")
    if template:
        html = template.draft_html or template.html
    elif data.role == "landing":
        title = name
        html = f'<main><h1>{escape(title)}</h1><p>Découvrez notre proposition.</p><button data-sillage-next="" type="button">Continuer</button></main>'
    else:
        html = blank_form_html(name)
    if data.role == "landing":
        next_page_id = tunnel.entry_page_id
        position = 0
        for page in pages:
            page.position += 1
    else:
        thanks = next((page for page in pages if page.role == "thanks"), None)
        next_page_id = thanks.id if thanks else None
        position = thanks.position if thanks else max((page.position for page in pages), default=-1) + 1
        for item in pages:
            if item.position >= position:
                item.position += 1
    cleaned, manifest = prepare_page(html, require_form=data.role == "form")
    page = Page(tunnel_id=tunnel.id, name=name, role=data.role, position=position,
                slug=unique_page_slug(db, name),
                next_page_id=next_page_id, html=cleaned, manifest=manifest)
    db.add(page)
    db.flush()
    if data.role == "landing":
        tunnel.entry_page_id = page.id
    else:
        predecessor = next((item for item in pages if item.next_page_id == next_page_id and item.id != page.id), None)
        if predecessor:
            predecessor.next_page_id = page.id
    db.commit()
    db.refresh(tunnel)
    return tunnel_json(tunnel, form)


@app.patch("/api/forms/{form_id}/tunnel/pages/{page_id}")
def update_tunnel_page(form_id: str, page_id: str, data: TunnelPageUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    tunnel = form_tunnel(db, form)
    page = next((item for item in tunnel.pages if item.id == page_id), None)
    if not page:
        raise HTTPException(404, "Page introuvable")
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Aucune modification transmise")
    if changes.get("name") and page.role != "thanks" and page.id != form.id:
        page.name = changes["name"]
        page.slug = unique_page_slug(db, changes["name"], exclude_page_id=page.id)
    if "settings" in changes:
        if page.role != "thanks":
            raise HTTPException(422, "Seule la page de remerciement accepte ces réglages")
        new_settings = changes["settings"]
        current_settings = page.settings or {}
        current_state = {**published_state(form), "thank_you": current_settings}
        if page.html == converted_html(form, current_state, role="thanks")[0]:
            next_state = {**current_state, "thank_you": new_settings}
            page.html, page.manifest = converted_html(form, next_state, role="thanks")
        page.settings = new_settings
        form.thank_you = {}
    if "next_page_id" in changes:
        target_id = changes["next_page_id"]
        if target_id is not None and target_id not in {item.id for item in tunnel.pages if item.id != page.id}:
            raise HTTPException(422, "La page suivante doit appartenir au même tunnel")
        target_page = next((item for item in tunnel.pages if item.id == target_id), None) if target_id else None
        if target_page and page.role != "form" and target_page.role == "thanks":
            has_prior_form = any(item.role == "form" and item.position < page.position for item in tunnel.pages)
            if not has_prior_form:
                raise HTTPException(422, "Le remerciement suit une soumission de formulaire")
        cursor = target_id
        seen = {page.id}
        lookup = {item.id: item for item in tunnel.pages}
        while cursor:
            if cursor in seen:
                raise HTTPException(422, "Le parcours ne peut pas former une boucle")
            seen.add(cursor)
            cursor = lookup[cursor].next_page_id
        page.next_page_id = target_id
    if "position" in changes and changes["position"] is not None:
        ordered = sorted((item for item in tunnel.pages if item.id != page.id), key=lambda item: item.position)
        ordered.insert(min(changes["position"], len(ordered)), page)
        if ordered[0].role == "thanks":
            raise HTTPException(422, "Le remerciement ne peut pas être la première page")
        if any(item.role == "thanks" for item in ordered[:-1]):
            raise HTTPException(422, "La page de remerciement doit rester à la fin du tunnel")
        for index, item in enumerate(ordered):
            item.position = index
            item.next_page_id = ordered[index + 1].id if index + 1 < len(ordered) else None
        tunnel.entry_page_id = ordered[0].id
    db.commit()
    db.refresh(tunnel)
    return tunnel_json(tunnel, form)


def revision_page(db: Session, form: Form, data: LunaRefineRequest) -> Page:
    if not data.page_id:
        return form_page(form, data.view)
    page = db.get(Page, data.page_id)
    if not page or page.tunnel_id != form_tunnel(db, form).id:
        raise HTTPException(404, "Page introuvable")
    return page


def page_revision_context(db: Session, form: Form, data: LunaRefineRequest) -> tuple[str, dict]:
    page = revision_page(db, form, data)
    current_html = page.draft_html or page.html
    selection = {
        "element_ids": data.element_ids,
        "label": data.selection_label,
        "view": data.view,
        "page_role": page.role,
        "region": data.region,
        "rect": data.selection_rect.model_dump() if data.selection_rect else None,
    }
    return current_html, {
        "selection": selection,
        "history": luna_history(form),
        "brief": form.brief or {},
        "stats": {"visits": page.visits, "conversions": page.conversions, "responses": count_responses(db, form.id)},
        "existing_names": [field["name"] for field in (page.draft_manifest if page.draft_html is not None else page.manifest) or []],
        "screenshot_data_url": data.screenshot_data_url,
        "images": data.images,
        "api_key": settings.openai_api_key,
        "model": settings.openai_model,
        "timeout_seconds": settings.openai_timeout_seconds,
    }


def save_page_revision(db: Session, form: Form, data: LunaRefineRequest, revision: dict, expected_html: str) -> dict:
    page = revision_page(db, form, data)
    db.refresh(page)
    if (page.draft_html or page.html) != expected_html:
        raise ValueError("La page a changé pendant la génération. Rechargez l'éditeur avant de réessayer.")
    try:
        candidate = merge_page_region(expected_html, revision["html"], revision.get("region"))
        cleaned_html, manifest = prepare_page(candidate, require_form=page.role == "form")
    except ValueError:
        db.rollback()
        raise

    if not any((version.snapshot or {}).get("page_id") == page.id for version in form.versions):
        record_version(db, form, {**published_state(form), "html": form_page(form).html,
                                  "thanks_html": form_page(form, "thanks").html,
                                  "page_id": page.id, "page_html": expected_html},
                       source="initial", message="Version publiée")
    form.draft = form.draft or published_state(form)
    page.draft_html, page.draft_manifest = cleaned_html, manifest
    thanks = form_page(form, "thanks")
    form_document = form_page(form)
    version = record_version(
        db, form,
        {**form.draft, "html": form_document.draft_html or form_document.html, "thanks_html": thanks.draft_html or thanks.html,
         "page_id": page.id, "page_html": cleaned_html},
        source="luna", instruction=data.instruction, message=revision["message"],
        screenshot_data_url=data.screenshot_data_url, images=data.images,
    )
    db.commit()
    db.refresh(form)
    return {
        "message": revision["message"],
        "form": form_json(db, form),
        "version": version_json(version),
        "touched": [revision["region"]] if revision.get("region") else [],
    }


@app.post("/api/forms/{form_id}/luna/refine")
def refine_with_luna(form_id: str, data: LunaRefineRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not settings.openai_api_key:
        raise HTTPException(503, "Ajoutez OPENAI_API_KEY dans votre fichier .env pour modifier la page avec Luna.")
    form = owned_form(form_id, db, user)
    current_html, context = page_revision_context(db, form, data)
    try:
        revision = revise_page(current_html, data.instruction, page_identity(form), **context)
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc
    try:
        return save_page_revision(db, form, data, revision, current_html)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/forms/{form_id}/luna/refine/stream")
def refine_with_luna_stream(form_id: str, data: LunaRefineRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not settings.openai_api_key:
        raise HTTPException(503, "Ajoutez OPENAI_API_KEY dans votre fichier .env pour modifier la page avec Luna.")
    # Authentification et propriété sont vérifiées avant d'ouvrir le flux.
    owned_form(form_id, db, user)
    company_id = user.company_id

    def event_stream():
        def send(payload: dict) -> str:
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        with SessionLocal() as stream_db:
            form = stream_db.get(Form, form_id)
            if not form or form.campaign.company_id != company_id:
                yield send({"type": "error", "message": "Formulaire introuvable"})
                return
            current_html, context = page_revision_context(stream_db, form, data)
            try:
                for event in stream_page_revision(current_html, data.instruction, page_identity(form), **context):
                    if event["type"] == "final":
                        result = save_page_revision(stream_db, form, data, event, current_html)
                        yield send({"type": "final", **result})
                    elif event["type"] in {"preview", "reset"}:
                        yield send(event)
            except (LunaAPIError, ValueError) as exc:
                stream_db.rollback()
                yield send({"type": "error", "message": str(exc)})
            except Exception:
                stream_db.rollback()
                logging.exception("La révision Luna en flux a échoué")
                yield send({"type": "error", "message": "La génération a échoué. Réessayez dans un instant."})

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/forms/{form_id}/versions")
def list_versions(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    return [version_json(version) for version in form.versions]


@app.patch("/api/forms/{form_id}/draft")
def update_draft(form_id: str, data: DraftUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Edition directe : ce qui est corrige a la main va aussi dans le brouillon."""
    form = owned_form(form_id, db, user)
    changes = data.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(422, "Aucune modification transmise")
    if form.draft is None and not form.versions:
        record_version(db, form, {**published_state(form), "html": form_page(form).html, "thanks_html": form_page(form, "thanks").html}, source="initial", message="Version publiée")
    html = changes.pop("html", None)
    form.draft = {**editing_state(form), **changes} if changes else form.draft or published_state(form)
    page = form_page(form)
    if html is not None:
        try:
            page.draft_html, page.draft_manifest = prepare_page(html, require_form=True)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    else:
        # Les anciens panneaux peuvent encore modifier les métadonnées. Le
        # document HTML reste toutefois la source visuelle et ne doit jamais
        # être reconstruit implicitement depuis ces anciennes colonnes.
        if page.draft_html is None:
            page.draft_html = page.html
            page.draft_manifest = page.manifest
    thanks = form_page(form, "thanks")
    record_version(db, form, {**form.draft, "html": page.draft_html, "thanks_html": thanks.draft_html or thanks.html}, source="manual", message="Modification manuelle")
    db.commit()
    db.refresh(form)
    return form_json(db, form)


@app.post("/api/forms/{form_id}/draft/publish")
def publish_draft(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    page = form_page(form)
    tunnel = form_tunnel(db, form)
    if not form.draft and not any(item.draft_html for item in tunnel.pages):
        raise HTTPException(422, "Aucune modification à publier")
    thanks = form_page(form, "thanks")
    previous_thanks = thank_you_settings(form)
    previous_thanks_html = converted_html(form, {**published_state(form), "thank_you": previous_thanks}, role="thanks")[0]
    draft_thanks_settings = (form.draft or {}).get("thank_you")
    for key, value in (form.draft or {}).items():
        if key in EDITABLE_KEYS:
            if key == "thank_you":
                thanks.settings = value
            else:
                setattr(form, key, value)
    if page.draft_html:
        page.html, page.manifest = prepare_page(page.draft_html, require_form=True)
        consent_field = next((field for field in form.fields if field.get("type") == "consent"), None)
        # Les anciennes clés restent dans FormResponse.answers et les exports.
        # Les garder parmi les champs actifs les ferait réapparaître lors de la
        # prochaine conversion d'un document historique.
        form.fields = [*page.manifest, *([consent_field] if consent_field else [])]
        page.draft_html = None
        page.draft_manifest = None
    if thanks.draft_html:
        thanks.html = thanks.draft_html
        thanks.draft_html = None
    elif draft_thanks_settings is not None and thanks.html == previous_thanks_html:
        thanks.html, thanks.manifest = converted_html(
            form, {**published_state(form), "thank_you": thanks.settings or {}}, role="thanks"
        )
    for extra in tunnel.pages:
        if extra.id in {page.id, thanks.id} or not extra.draft_html:
            continue
        extra.html, extra.manifest = prepare_page(extra.draft_html, require_form=extra.role == "form")
        extra.draft_html = None
        extra.draft_manifest = None
    form.draft = None
    record_version(db, form, {**published_state(form), "html": page.html, "thanks_html": thanks.html}, source="publish", message="Modifications publiées")
    db.commit()
    db.refresh(form)
    return form_json(db, form)


@app.post("/api/forms/{form_id}/draft/discard")
def discard_draft(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    form.draft = None
    for page in form_tunnel(db, form).pages:
        page.draft_html = None
        page.draft_manifest = None
    db.commit()
    db.refresh(form)
    return form_json(db, form)


@app.post("/api/forms/{form_id}/versions/{version_id}/restore")
def restore_version(form_id: str, version_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Annuler, c'est revenir a une version precedente : rien n'est perdu."""
    form = owned_form(form_id, db, user)
    version = db.get(FormVersion, version_id)
    if not version or version.form_id != form.id:
        raise HTTPException(404, "Version introuvable")
    form.draft = {key: value for key, value in version.snapshot.items() if key in EDITABLE_KEYS}
    page = form_page(form)
    page.draft_html, page.draft_manifest = prepare_page(version.snapshot["html"], require_form=True) if version.snapshot.get("html") else converted_html(form, editing_state(form))
    thanks = form_page(form, "thanks")
    thanks.draft_html, _ = prepare_page(version.snapshot["thanks_html"], require_form=False) if version.snapshot.get("thanks_html") else converted_html(form, editing_state(form), role="thanks")
    restored_page_id = version.snapshot.get("page_id")
    if restored_page_id and restored_page_id not in {page.id, thanks.id}:
        extra = db.get(Page, restored_page_id)
        if extra and extra.tunnel_id == form_tunnel(db, form).id:
            extra.draft_html, extra.draft_manifest = prepare_page(
                version.snapshot.get("page_html") or extra.html, require_form=extra.role == "form"
            )
    restored_snapshot = {**form.draft, "html": page.draft_html,
                         "thanks_html": thanks.draft_html, "_restored_to_version_id": version.id}
    if restored_page_id:
        restored_snapshot.update(page_id=restored_page_id, page_html=extra.draft_html if restored_page_id not in {page.id, thanks.id} and extra else page.draft_html)
    record_version(db, form, restored_snapshot, source="restore", message="Retour à une version précédente")
    db.commit()
    db.refresh(form)
    return form_json(db, form)


@app.post("/api/forms/{form_id}/duplicate", status_code=201)
def duplicate_form(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = owned_form(form_id, db, user)
    name = f"{source.name} - copie"
    copy = Form(campaign_id=source.campaign_id, creator_id=user.id, identity=page_identity(source), name=name, slug=unique_slug(db, name), description=source.description, kind=source.kind, fields=source.fields, design=source.design or default_design(), content=source.content or default_content(source.kind), thank_you=thank_you_settings(source), visibility="private")
    db.add(copy)
    copy_form_pages(db, source, copy)
    db.commit()
    db.refresh(copy)
    return form_json(db, copy)


@app.get("/api/forms/{form_id}/responses")
def form_responses(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    rows = db.scalars(select(FormResponse).where(FormResponse.form_id == form.id).order_by(desc(FormResponse.created_at))).all()
    return [response_json(r) for r in rows]


@app.get("/api/forms/{form_id}/export.csv")
def export_form_csv(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    rows = db.scalars(select(FormResponse).where(FormResponse.form_id == form.id)).all()
    return csv_response(rows, f"{form.slug}.csv")


# --- Bibliotheque ------------------------------------------------------------


@app.get("/api/library")
def library(db: Session = Depends(get_db), user: User = Depends(current_user)):
    saved = db.scalars(select(Template).where(Template.company_id == user.company_id).order_by(desc(Template.updated_at))).all()
    recent = db.scalars(
        select(Form).join(Campaign, Form.campaign_id == Campaign.id)
        .where(Campaign.company_id == user.company_id, Campaign.archived.is_(False), Form.archived.is_(False))
        .order_by(desc(Form.updated_at)).limit(4)
    ).all()
    return {
        "featured": [template_preview(template_payload(template), user.company) for template in CURATED_TEMPLATES],
        "saved": [saved_template_json(template, user.company) for template in saved],
        "recent": [form_json(db, form) for form in recent],
    }


@app.post("/api/library/featured/{template_key}/save", status_code=201)
def save_featured_template(template_key: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = curated_template(template_key)
    if not source:
        raise HTTPException(404, "Modèle introuvable")
    existing = db.scalar(select(Template).where(Template.company_id == user.company_id, Template.source_key == template_key))
    if existing:
        return saved_template_json(existing, user.company)
    payload = template_payload(source)
    saved = Template(
        company_id=user.company_id,
        source_key=template_key,
        name=payload["name"],
        description=payload["description"],
        category=payload["category"],
        fields=payload["fields"],
        design=payload["design"],
        thank_you=payload["thank_you"],
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return saved_template_json(saved, user.company)


@app.post("/api/library/featured/{template_key}/use", status_code=201)
def use_featured_template(template_key: str, data: TemplateUse, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = curated_template(template_key)
    if not source:
        raise HTTPException(404, "Modèle introuvable")
    campaign = owned_campaign(data.campaign_id, db, user)
    form = form_from_template(db, template_payload(source), user, campaign)
    db.add(form)
    create_form_pages(db, form)
    db.commit()
    db.refresh(form)
    return form_json(db, form)


@app.post("/api/library/templates/{template_id}/use", status_code=201)
def use_saved_template(template_id: str, data: TemplateUse, db: Session = Depends(get_db), user: User = Depends(current_user)):
    template = db.get(Template, template_id)
    if not template or template.company_id != user.company_id:
        raise HTTPException(404, "Modèle introuvable")
    campaign = owned_campaign(data.campaign_id, db, user)
    form = form_from_template(db, saved_template_json(template), user, campaign)
    template.uses += 1
    db.add(form)
    create_form_pages(db, form)
    db.commit()
    db.refresh(form)
    return form_json(db, form)


# --- Boite de reception ------------------------------------------------------


def response_json(r: FormResponse, *, with_form: bool = False):
    payload = {"id": r.id, "answers": r.answers, "source": r.source, "promo_code": r.promo_code, "consent": r.consent, "consent_text": r.consent_text, "ip_address": r.ip_address, "user_agent": r.user_agent, "created_at": r.created_at.isoformat()}
    if with_form:
        payload |= {"form_id": r.form_id, "form": r.form.name, "campaign_id": r.form.campaign_id, "campaign": r.form.campaign.name}
    return payload


def inbox_query(user: User, campaign_id: str, form_id: str, source: str, date_from: date | None, date_to: date | None, q: str):
    """Filtres de la boite de reception, partages par la liste et l'export."""
    conditions = [Campaign.company_id == user.company_id]
    if campaign_id:
        conditions.append(Form.campaign_id == campaign_id)
    if form_id:
        conditions.append(FormResponse.form_id == form_id)
    if source:
        conditions.append(FormResponse.source == source)
    if date_from:
        conditions.append(FormResponse.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        conditions.append(FormResponse.created_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc))
    if q.strip():
        conditions.append(answers_contain(q.strip()))
    return conditions


def like_pattern(value: str) -> str:
    return "%" + value.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def answers_contain(needle: str):
    """Recherche plein texte dans les reponses, quelle que soit la base."""
    answers = cast(FormResponse.answers, Text)
    # Les reponses enregistrees avant que le JSON passe en UTF-8 gardent les accents echappes.
    escaped = json.dumps(needle, ensure_ascii=True)[1:-1]
    terms = [answers.ilike(like_pattern(needle), escape="!")]
    if escaped != needle:
        terms.append(answers.ilike(like_pattern(escaped), escape="!"))
    return or_(*terms)


@app.get("/api/responses")
def list_responses(
    campaign_id: str = "",
    form_id: str = "",
    source: str = "",
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    q: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    conditions = inbox_query(user, campaign_id, form_id, source, date_from, date_to, q)
    base = select(FormResponse).join(FormResponse.form).join(Form.campaign).where(*conditions)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(desc(FormResponse.created_at)).limit(limit).offset(offset)).all()
    sources = db.execute(
        select(FormResponse.source).join(FormResponse.form).join(Form.campaign)
        .where(Campaign.company_id == user.company_id).group_by(FormResponse.source).order_by(FormResponse.source)
    ).scalars().all()
    return {"items": [response_json(r, with_form=True) for r in rows], "total": total, "limit": limit, "offset": offset, "sources": list(sources)}


@app.get("/api/responses/export.csv")
def export_responses_csv(
    campaign_id: str = "",
    form_id: str = "",
    source: str = "",
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    conditions = inbox_query(user, campaign_id, form_id, source, date_from, date_to, q)
    rows = db.scalars(select(FormResponse).join(FormResponse.form).join(Form.campaign).where(*conditions).order_by(desc(FormResponse.created_at))).all()
    return csv_response(rows, "reponses.csv", with_form=True)


def csv_response(rows: list[FormResponse], filename: str, *, with_form: bool = False):
    keys = list(dict.fromkeys(k for r in rows for k in r.answers.keys()))
    head = ["date", "campagne", "formulaire", "source", "consent"] if with_form else ["date", "source", "consent"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[*head, *keys])
    writer.writeheader()
    for r in rows:
        row = {"date": r.created_at.isoformat(), "source": r.source, "consent": r.consent, **r.answers}
        if with_form:
            row |= {"campagne": r.form.campaign.name, "formulaire": r.form.name}
        writer.writerow(row)
    return StreamingResponse(iter([buffer.getvalue().encode("utf-8-sig")]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.delete("/api/responses/{response_id}", status_code=204)
def delete_response(response_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    response = db.get(FormResponse, response_id)
    if not response or response.form.campaign.company_id != user.company_id:
        raise HTTPException(404, "Réponse introuvable")
    db.delete(response)
    db.commit()


# --- Formulaire public -------------------------------------------------------


@app.get("/api/public/{slug}")
def public_form(slug: str, page_id: str | None = None, db: Session = Depends(get_db)):
    form = db.scalar(select(Form).where(Form.slug == slug, Form.archived.is_(False)))
    if not form or form.campaign.archived:
        raise HTTPException(404, "Formulaire introuvable")
    c = form.campaign.company
    tunnel = form_tunnel(db, form)
    entry_page = db.get(Page, tunnel.entry_page_id)
    page = db.get(Page, page_id) if page_id else entry_page
    if not entry_page or entry_page.tunnel_id != tunnel.id or not page or page.tunnel_id != tunnel.id:
        raise HTTPException(404, "Page d'entrée introuvable")
    legal = consent_text(form)
    return {"name": form.name, "description": form.description, "fields": form.fields, "design": form.design or default_design(), "content": form.content or default_content(form.kind), "thank_you": thank_you_settings(form), "status": form.status, "current_page_id": page.id, "html": render_page(page.html, legal), "thanks_html": "", "manifest": page.manifest, "company": {"name": c.name, "legal_name": c.legal_name, "address": c.address, "primary_color": c.primary_color, "accent_color": c.accent_color, "dpo_email": c.dpo_email, "logo": c.logo}, "tunnel": {"id": tunnel.id, "entry_page_id": tunnel.entry_page_id, "pages": [{"id": item.id, "role": item.role, "position": item.position, "next_page_id": item.next_page_id, "visits": item.visits, "conversions": item.conversions} for item in sorted(tunnel.pages, key=lambda item: item.position)]}}


def live_form(slug: str, db: Session) -> Form | None:
    form = db.scalar(select(Form).where(Form.slug == slug, Form.status == "active", Form.archived.is_(False)))
    return form if form and not form.campaign.archived else None


def journey_cookie(request: Request, tunnel: Tunnel) -> dict | None:
    token = request.cookies.get("sillage_journey")
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return payload if payload.get("tunnel") == tunnel.id else None


def set_journey_cookie(response: Response, request: Request, payload: dict) -> str:
    token = jwt.encode({**payload, "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, settings.secret_key, algorithm="HS256")
    response.set_cookie("sillage_journey", token, max_age=3600, httponly=True,
                        secure=request.url.scheme == "https", samesite="lax", path="/api/public")
    return token


def public_page_json(page: Page, form: Form, answers: dict | None = None) -> dict:
    return {"page_id": page.id, "role": page.role, "html": render_page(page.html, consent_text(form), answers),
            "manifest": page.manifest, "next_page_id": page.next_page_id}


@app.post("/api/public/{slug}/visit")
def track_visit(slug: str, request: Request, response: Response, data: PublicPageVisit | None = None, db: Session = Depends(get_db)):
    """Compte chaque étape au premier affichage du parcours, jamais sur GET."""
    form = live_form(slug, db)
    if not form:
        raise HTTPException(404, "Tunnel indisponible")
    tunnel = form_tunnel(db, form)
    page_id = data.page_id if data and data.page_id else tunnel.entry_page_id
    page = db.get(Page, page_id)
    if not page or page.tunnel_id != tunnel.id:
        raise HTTPException(404, "Page introuvable")
    previous = journey_cookie(request, tunnel)
    if page.id != tunnel.entry_page_id and (not previous or previous.get("page") != page.id):
        raise HTTPException(403, "Étape inaccessible")
    if page.role == "thanks" and not (previous and previous.get("submitted")):
        raise HTTPException(403, "Étape inaccessible")
    visited = list(previous.get("visited", [])) if previous else []
    if page.id not in visited:
        page.visits += 1
        if page.role == "form":
            form.visits += 1
        visited.append(page.id)
        db.commit()
    response_id = previous.get("response_id") if previous else None
    answers = None
    if page.role == "thanks" and response_id:
        stored = db.get(FormResponse, response_id)
        answers = stored.answers if stored and stored.form_id == form.id else None
    set_journey_cookie(response, request, {"tunnel": tunnel.id, "page": page.id,
                       "sid": previous.get("sid") if previous else str(uuid4()),
                       "visited": visited, "submitted": bool(previous and previous.get("submitted")),
                       "response_id": response_id})
    return public_page_json(page, form, answers)


@app.post("/api/public/{slug}/advance")
def advance_public_page(slug: str, data: PublicPageAdvance, request: Request, response: Response, db: Session = Depends(get_db)):
    form = live_form(slug, db)
    if not form:
        raise HTTPException(404, "Tunnel indisponible")
    tunnel = form_tunnel(db, form)
    journey = journey_cookie(request, tunnel)
    if not journey or journey.get("page") != data.from_page_id:
        raise HTTPException(403, "Étape inaccessible")
    current = db.get(Page, data.from_page_id)
    target = db.get(Page, current.next_page_id) if current and current.tunnel_id == tunnel.id and current.next_page_id else None
    if not target or target.tunnel_id != tunnel.id:
        raise HTTPException(422, "Aucune étape suivante disponible")
    if target.role == "thanks" and not journey.get("submitted"):
        raise HTTPException(422, "Le remerciement suit une soumission de formulaire")
    visited = list(journey.get("visited", []))
    if target.id not in visited:
        current.conversions += 1
        target.visits += 1
        if target.role == "form":
            form.visits += 1
        visited.append(target.id)
        db.commit()
    set_journey_cookie(response, request, {**journey, "page": target.id, "visited": visited})
    return public_page_json(target, form)


@app.post("/api/public/{slug}/submit", status_code=201)
def submit(slug: str, data: SubmitResponse, request: Request, response: Response, db: Session = Depends(get_db)):
    form = live_form(slug, db)
    if not form:
        raise HTTPException(404, "Ce formulaire n'accepte pas de réponse")
    tunnel = form_tunnel(db, form)
    page = db.get(Page, data.page_id) if data.page_id else form_page(form)
    if not page or page.tunnel_id != tunnel.id or page.role != "form":
        raise HTTPException(404, "Page de formulaire introuvable")
    journey = journey_cookie(request, tunnel)
    if (journey and journey.get("page") != page.id) or (not journey and page.id != tunnel.entry_page_id):
        raise HTTPException(403, "Étape inaccessible")
    names = {field["name"] for field in page.manifest}
    if set(data.answers) - names:
        raise HTTPException(422, "La réponse contient des champs inconnus")
    required = [field for field in page.manifest if field.get("required")]
    missing = [field["label"] for field in required if data.answers.get(field["name"]) in (None, "", [])]
    if missing:
        raise HTTPException(422, f"Champs requis : {', '.join(missing)}")
    if not any(field.get("type") != "consent" for field in page.manifest):
        raise HTTPException(422, "Ajoutez au moins un champ avant de collecter une réponse")
    if not data.consent:
        raise HTTPException(422, "Le consentement est requis")
    row = FormResponse(form_id=form.id, answers=data.answers, source=data.source, promo_code=data.promo_code, consent=data.consent, consent_text=consent_text(form), ip_address=request.client.host if request.client else "", user_agent=request.headers.get("user-agent", "")[:300])
    db.add(row)
    page.conversions += 1
    next_page = db.get(Page, page.next_page_id) if page.next_page_id else form_page(form, "thanks")
    if next_page and next_page.tunnel_id != tunnel.id:
        raise HTTPException(422, "La page suivante est invalide")
    if next_page:
        next_page.visits += 1
    db.commit()
    visited = list(journey.get("visited", [])) if journey else [page.id]
    if next_page and next_page.id not in visited:
        visited.append(next_page.id)
    token = set_journey_cookie(response, request, {"tunnel": tunnel.id,
                               "page": next_page.id if next_page else page.id,
                               "sid": journey.get("sid") if journey else str(uuid4()),
                               "visited": visited, "submitted": True, "response_id": row.id})
    return {
        "id": row.id,
        "thank_you": thank_you_settings(form),
        "next_page_id": next_page.id if next_page else None,
        "thanks_html": render_page(next_page.html, "", data.answers) if next_page else "",
        "html": render_page(next_page.html, consent_text(form), data.answers) if next_page else "",
        "manifest": next_page.manifest if next_page else [],
        "journey_token": token,
    }
