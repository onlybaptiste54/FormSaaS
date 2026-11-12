"""Guided, form-independent sales funnels and their public journey."""

import io
import json
import math
import random
import zipfile
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator
from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .luna import LunaAPIError, merge_page_region, revise_page, slugify
from .models import Campaign, Company, Page, PageVariant, PageVersion, Tunnel, TunnelEvent, User
from .page_document import RESERVED_SLUGS, free_slug, prepare_page, public_document, render_page, same_document
from .security import client_ip, current_user, rate_limit, write_user


router = APIRouter()

# Les trois routes du parcours public ecrivent en base a chaque appel. La
# deduplication borne les lignes d'une session, mais fabriquer des sessions
# neuves est gratuit : sans plafond, un script gonfle les compteurs et fait
# grossir tunnel_events sans fin. Un seul seau pour les trois, sinon le budget
# serait triple. Large : un parcours honnete coute trois a cinq appels.
JOURNEY_CALLS, JOURNEY_WINDOW = 120, 10 * 60
# Meme plafond que les tunnels de formulaire.
MAX_STEPS = 20
# Au-dela, aucune des versions ne recoit assez de visites pour trancher.
MAX_VARIANTS = 3

SALES_PAGE_INSTRUCTIONS = """Tu es Luna, directrice artistique et conceptrice de tunnels de vente.
Tu produis exclusivement le JSON demandé : message, html et region. Le HTML est un document complet, en français, avec un seul bloc <style> et une composition responsive soignée. Utilise la marque et le brief commercial fournis ; ne crée ni témoignage, ni chiffre, ni garantie, ni certification non fournis. Les pages s'adressent aux visiteurs, sans commentaire sur ton travail. Aucun script, iframe, formulaire, lien de paiement inventé ou ressource externe non fournie. Une image ne peut provenir que de identity.images. Balise les sections avec data-sillage-region. Tu peux dessiner en SVG en ligne (icônes, séparateurs, dégradés) sans script ni référence externe, et utiliser href="mailto:…", href="tel:…" ou une ancre href="#identifiant" vers une section de la page. Sur la page d'ouverture, termine par un bouton <button type="button" data-sillage-next>Découvrir l'offre</button>. Sur une étape intermédiaire, termine par un bouton <button type="button" data-sillage-next>...</button> dont le libellé invite à continuer. Sur la page d'offre, termine par un bouton <button type="button" data-sillage-goal>...</button> dont le libellé reprend exactement l'action du brief. Le serveur gère ces actions ; ne leur mets aucune URL. Pour une retouche, garde tout le reste de la page, et réponds avec html vide si la demande est une simple question. Une région partielle doit contenir sa balise racine complète ; region="style" contient le bloc style complet."""


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
    variant_id: str = Field(default="", max_length=36)


class SalesDestinationUpdate(BaseModel):
    goal_url: str = Field(max_length=2048)

    @field_validator("goal_url")
    @classmethod
    def https_url(cls, value: str) -> str:
        return SalesTunnelCreate.https_url(SalesTunnelCreate.required_destination(value.strip()))


def owned_tunnel(tunnel_id: str, db: Session, user: User) -> Tunnel:
    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel or tunnel.kind != "sales" or tunnel.campaign.company_id != user.company_id:
        raise HTTPException(404, "Tunnel introuvable")
    return tunnel


def page_payload(page: Page, *, draft: bool = False) -> dict:
    html = page.draft_html if draft and page.draft_html else page.html
    return {"id": page.id, "name": page.name, "slug": page.slug, "role": page.role, "position": page.position,
            "next_page_id": page.next_page_id, "html": render_page(html, ""),
            "has_draft": page.draft_html is not None, "visits": page.visits, "conversions": page.conversions,
            "variants": [{"id": item.id, "name": item.name,
                          "html": render_page(item.draft_html or item.html, ""),
                          "has_draft": item.draft_html is not None}
                         for item in page.variants]}


def tunnel_payload(tunnel: Tunnel) -> dict:
    pages = sorted(tunnel.pages, key=lambda page: page.position)
    return {"id": tunnel.id, "name": tunnel.name, "slug": tunnel.slug, "status": tunnel.status,
            "kind": tunnel.kind, "brief": tunnel.brief or {}, "goal_label": tunnel.goal_label,
            "goal_url": tunnel.goal_url, "entry_page_id": tunnel.entry_page_id,
            "seo": tunnel_seo(tunnel),
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


def has_action(html: str, action: str) -> bool:
    checker = _SalesActionCheck(action)
    checker.feed(html)
    return checker.valid_button


def collects_data(html: str) -> bool:
    checker = _SalesActionCheck("data-sillage-next")
    checker.feed(html)
    return checker.has_form


def validate_sales_page(html: str, *, has_next: bool) -> None:
    """L'action attendue vient de la place de la page, plus de son role.

    Une etape suivie d'une autre porte le bouton de passage ; la derniere porte
    le bouton d'action finale, sinon le parcours n'a pas de sortie. Le bouton
    final reste autorise sur une etape intermediaire : un visiteur convaincu
    plus tot doit pouvoir partir tout de suite. Le passage, lui, n'a aucun sens
    sur la derniere.
    """
    if collects_data(html):
        raise ValueError("Cette étape ne doit pas collecter de données personnelles.")
    if has_next:
        if not has_action(html, "data-sillage-next"):
            raise ValueError("Cette étape doit comporter un bouton de passage à la suivante.")
        return
    if not has_action(html, "data-sillage-goal"):
        raise ValueError("La dernière étape doit comporter le bouton d'action finale.")
    if has_action(html, "data-sillage-next"):
        raise ValueError("La dernière étape ne peut pas renvoyer vers une étape suivante.")


def relink(tunnel: Tunnel, ordered: list[Page]) -> None:
    """Reecrit les positions et la chaine depuis une seule liste ordonnee.

    L'ajout, la suppression et le deplacement passent tous par ici : la
    position et next_page_id ne peuvent donc pas se contredire.
    """
    for index, page in enumerate(ordered):
        page.position = index
        page.next_page_id = ordered[index + 1].id if index + 1 < len(ordered) else None
    tunnel.entry_page_id = ordered[0].id if ordered else None


def action_warnings(ordered: list[Page]) -> list[str]:
    """Signale les etapes dont le bouton ne correspond plus a leur place.

    On ne refuse pas le deplacement : on le dit, et l'utilisateur retouche la
    page avec Luna. Refuser rendrait le reordonnancement impraticable.
    """
    messages = []
    for index, page in enumerate(ordered):
        html = page.draft_html or page.html
        if index + 1 < len(ordered):
            if not has_action(html, "data-sillage-next"):
                messages.append(f"« {page.name} » n'a plus de bouton vers l'étape suivante.")
        elif not has_action(html, "data-sillage-goal"):
            messages.append(f"« {page.name} » est la dernière étape mais n'a pas le bouton d'action finale.")
    return messages


def generate_step(brief: dict, identity: dict, *, role: str, instruction: str,
                  has_next: bool) -> tuple[str, list[dict]]:
    result = revise_page(
        "", instruction, identity,
        selection={"view": role, "page_role": role, "element_ids": [], "label": "Nouvelle page"},
        brief=brief, api_key=settings.openai_api_key, model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds, page_instructions=SALES_PAGE_INSTRUCTIONS,
    )
    if result["region"] is not None:
        raise ValueError("Luna doit créer une page entière.")
    html, manifest = prepare_page(result["html"], require_form=False)
    validate_sales_page(html, has_next=has_next)
    if manifest:
        raise ValueError("Cette étape ne doit pas collecter de données personnelles.")
    return html, manifest


LANDING_INSTRUCTION = ("Crée la première page du tunnel : une accroche forte qui présente le besoin, "
                       "la promesse et les points forts vérifiés, puis invite à découvrir l'offre.")


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
        brief = data.model_dump()
        landing_html, landing_manifest = generate_step(
            brief, identity, role="landing", instruction=LANDING_INSTRUCTION, has_next=True)
        offer_html, offer_manifest = generate_step(
            brief, identity, role="offer", has_next=False,
            instruction="Crée la page d'offre : explique concrètement l'offre, réponds aux objections "
                        f"que le brief permet de traiter, puis termine par l'action « {data.goal_label} ».")
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    campaign = Campaign(company_id=user.company_id, creator_id=user.id, name=data.name,
                        objective=data.offer)
    db.add(campaign)
    db.flush()
    tunnel = Tunnel(campaign_id=campaign.id, name=data.name, slug=slugify(data.name),
                    status="draft", kind="sales", brief=brief, identity=identity,
                    goal_url=data.goal_url, goal_label=data.goal_label)
    db.add(tunnel)
    db.flush()
    landing = Page(tunnel_id=tunnel.id, name="Découverte", role="landing", position=0,
                   slug=step_slug(db, "Découverte"),
                   html=landing_html, manifest=landing_manifest)
    offer = Page(tunnel_id=tunnel.id, name="L'offre", role="offer", position=1,
                 slug=step_slug(db, "L'offre"),
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
    page = owned_page(tunnel, page_id)
    cible = page
    if data.variant_id:
        cible = next((item for item in page.variants if item.id == data.variant_id), None)
        if not cible:
            raise HTTPException(404, "Version introuvable")
    current = cible.draft_html or cible.html
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
        validate_sales_page(html, has_next=page.next_page_id is not None)
        if manifest:
            raise ValueError("La page doit garder son bouton d'action et ne pas contenir de formulaire.")
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if same_document(html, current):
        return {"message": "La page est déjà conforme à cette demande.", "changed": False,
                "tunnel": tunnel_payload(tunnel)}
    cible.draft_html = html
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
    for variante in page.variants:
        variante.draft_html = None
    db.commit()
    return tunnel_payload(tunnel)


class SalesStepCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    instruction: str = Field(min_length=10, max_length=800)


class SalesStepMove(BaseModel):
    position: int = Field(ge=0, le=19)


@router.post("/api/sales-funnels/{tunnel_id}/pages", status_code=201)
def add_sales_step(tunnel_id: str, data: SalesStepCreate, db: Session = Depends(get_db),
                   user: User = Depends(write_user)):
    """Insère une étape avant la dernière, qui garde l'action finale."""
    if not settings.openai_api_key:
        raise HTTPException(503, "Configurez Luna pour ajouter une étape.")
    tunnel = owned_tunnel(tunnel_id, db, user)
    ordered = sorted(tunnel.pages, key=lambda page: page.position)
    if len(ordered) >= MAX_STEPS:
        raise HTTPException(422, f"Le tunnel est limité à {MAX_STEPS} étapes.")
    try:
        html, manifest = generate_step(
            tunnel.brief or {}, tunnel.identity or {}, role="step", has_next=True,
            instruction=f"Crée une étape intermédiaire du tunnel, placée avant la page d'offre. "
                        f"{data.instruction}",
        )
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    page = Page(tunnel_id=tunnel.id, name=data.name.strip(), role="step",
                slug=step_slug(db, data.name.strip()),
                position=len(ordered), html=html, manifest=manifest)
    db.add(page)
    db.flush()
    relink(tunnel, [*ordered[:-1], page, ordered[-1]])
    db.commit()
    db.refresh(tunnel)
    return {"tunnel": tunnel_payload(tunnel),
            "warnings": action_warnings(sorted(tunnel.pages, key=lambda item: item.position))}


@router.patch("/api/sales-funnels/{tunnel_id}/pages/{page_id}")
def move_sales_step(tunnel_id: str, page_id: str, data: SalesStepMove,
                    db: Session = Depends(get_db), user: User = Depends(write_user)):
    """Déplace une étape. Le bouton d'une page peut ne plus convenir à sa
    nouvelle place : on le signale au lieu de refuser, sinon réordonner serait
    impraticable."""
    tunnel = owned_tunnel(tunnel_id, db, user)
    ordered = sorted(tunnel.pages, key=lambda page: page.position)
    page = next((item for item in ordered if item.id == page_id), None)
    if not page:
        raise HTTPException(404, "Étape introuvable")
    if data.position >= len(ordered):
        raise HTTPException(422, "Cette place n'existe pas dans le parcours.")
    ordered.remove(page)
    ordered.insert(data.position, page)
    relink(tunnel, ordered)
    db.commit()
    db.refresh(tunnel)
    return {"tunnel": tunnel_payload(tunnel), "warnings": action_warnings(ordered)}


@router.delete("/api/sales-funnels/{tunnel_id}/pages/{page_id}")
def delete_sales_step(tunnel_id: str, page_id: str, db: Session = Depends(get_db),
                      user: User = Depends(write_user)):
    """Retire une étape, et avec elle sa mesure.

    Les événements portent une clé étrangère vers la page : les garder la
    laisserait référencée. Supprimer une étape fait donc disparaître ses
    chiffres, et la réponse dit combien.
    """
    tunnel = owned_tunnel(tunnel_id, db, user)
    ordered = sorted(tunnel.pages, key=lambda page: page.position)
    page = next((item for item in ordered if item.id == page_id), None)
    if not page:
        raise HTTPException(404, "Étape introuvable")
    if len(ordered) <= 2:
        raise HTTPException(422, "Un tunnel garde au moins deux étapes.")
    measured = db.scalar(select(func.count(TunnelEvent.id)).where(TunnelEvent.page_id == page.id)) or 0
    db.execute(TunnelEvent.__table__.delete().where(TunnelEvent.page_id == page.id))
    ordered.remove(page)
    relink(tunnel, ordered)
    db.delete(page)
    db.commit()
    db.refresh(tunnel)
    warnings = action_warnings(sorted(tunnel.pages, key=lambda item: item.position))
    if measured:
        warnings.append(f"{measured} mesures de cette étape ont été supprimées avec elle.")
    return {"tunnel": tunnel_payload(tunnel), "warnings": warnings}


class SalesSeoUpdate(BaseModel):
    title: str = Field(default="", max_length=70)
    description: str = Field(default="", max_length=160)

    @field_validator("title", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


# En deca, l'ecart observe ne distingue rien : c'est du bruit. Le minimum de
# visites evite de conclure sur une poignee de passages, et la regle des cinq
# conversions attendues est la condition d'emploi du test lui-meme.
MIN_VISITS_PER_VERSION = 30
MIN_EXPECTED = 5
CONFIDENT_AT = 0.95


def _normal_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


def compare_versions(temoin: tuple[int, int], variante: tuple[int, int]) -> dict:
    """Dit si l'ecart entre deux versions se distingue du hasard.

    Test de comparaison de deux proportions. Il n'est valable qu'au-dela d'un
    certain nombre de passages : en dessous, on le dit plutot que d'afficher un
    pourcentage qui ferait trancher sur du bruit.
    """
    vues_a, buts_a = temoin
    vues_b, buts_b = variante
    manquantes = max(MIN_VISITS_PER_VERSION - vues_a, MIN_VISITS_PER_VERSION - vues_b, 0)
    if manquantes:
        return {"state": "insufficient", "confidence": None,
                "message": f"Pas encore de quoi trancher : {manquantes} visites de plus sur la version la moins vue."}

    part = (buts_a + buts_b) / (vues_a + vues_b)
    attendus = min(vues_a * part, vues_a * (1 - part), vues_b * part, vues_b * (1 - part))
    if attendus < MIN_EXPECTED:
        return {"state": "insufficient", "confidence": None,
                "message": "Pas encore de quoi trancher : trop peu de clics finaux pour comparer."}

    ecart = buts_b / vues_b - buts_a / vues_a
    erreur = math.sqrt(part * (1 - part) * (1 / vues_a + 1 / vues_b))
    if not erreur:
        return {"state": "inconclusive", "confidence": 0.0,
                "message": "Les deux versions font exactement jeu égal."}
    # Plafonne a 99 % : aucune mesure ne donne une certitude.
    confiance = min(2 * _normal_cdf(abs(ecart) / erreur) - 1, 0.99)
    if confiance < CONFIDENT_AT:
        return {"state": "inconclusive", "confidence": round(confiance, 3),
                "message": f"Écart non concluant : il peut venir du hasard ({round(confiance * 100)} % de certitude)."}
    gagnante = "Cette version" if ecart > 0 else "La version témoin"
    return {"state": "confident", "confidence": round(confiance, 3),
            "message": f"{gagnante} l'emporte, avec {round(confiance * 100)} % de certitude."}


def tunnel_seo(tunnel: Tunnel) -> dict:
    """Ce que montrent un moteur de recherche et l'aperçu d'un lien partagé.

    Vides, le titre et la description retombent sur le nom du tunnel et son
    offre : une page publiée porte toujours une référence correcte, même si
    personne n'a rempli ces deux champs.
    """
    offer = str((tunnel.brief or {}).get("offer", "")).strip()
    description = tunnel.seo_description or offer
    return {"title": tunnel.seo_title or tunnel.name,
            "description": description[:160],
            "custom": bool(tunnel.seo_title or tunnel.seo_description)}


@router.patch("/api/sales-funnels/{tunnel_id}/seo")
def update_sales_seo(tunnel_id: str, data: SalesSeoUpdate, db: Session = Depends(get_db),
                     user: User = Depends(write_user)):
    tunnel = owned_tunnel(tunnel_id, db, user)
    tunnel.seo_title = data.title or None
    tunnel.seo_description = data.description or None
    db.commit()
    db.refresh(tunnel)
    return tunnel_payload(tunnel)


@router.get("/api/public/sales/{slug}/meta")
def sales_meta(slug: str, db: Session = Depends(get_db)):
    """Référence d'une page publiée, pour le rendu serveur du front.

    Publique et sans jeton, comme la page qu'elle décrit, et sans rien compter :
    un robot qui lit la référence n'est pas une visite.
    """
    tunnel = live_tunnel(slug, db)
    entry = db.get(Page, tunnel.entry_page_id)
    if not entry:
        raise HTTPException(404, "Tunnel indisponible")
    return {**tunnel_seo(tunnel), "name": tunnel.name, "updated_at": tunnel.updated_at.isoformat(),
            "html": render_page(entry.html, "")}


@router.get("/api/public/sales-sitemap")
def sales_sitemap(db: Session = Depends(get_db)):
    """Les tunnels en ligne, pour le sitemap du front. Rien de privé ici : ce
    sont exactement les adresses que l'on souhaite voir indexées."""
    tunnels = db.scalars(
        select(Tunnel).join(Campaign, Tunnel.campaign_id == Campaign.id)
        .where(Tunnel.kind == "sales", Tunnel.status == "active", Campaign.archived.is_(False))
    ).all()
    return [{"slug": tunnel.slug, "updated_at": tunnel.updated_at.isoformat()} for tunnel in tunnels]


class SalesVariantCreate(BaseModel):
    name: str = Field(default="", max_length=60)


def owned_page(tunnel: Tunnel, page_id: str) -> Page:
    page = next((item for item in tunnel.pages if item.id == page_id), None)
    if not page:
        raise HTTPException(404, "Étape introuvable")
    return page


def drop_variant_events(db: Session, variant_ids: list[str]) -> int:
    """Oublie la mesure des versions qui disparaissent.

    Une fois la comparaison tranchee, garder des lignes qui designent une
    version supprimee ne dit plus rien a personne.
    """
    if not variant_ids:
        return 0
    compte = db.scalar(select(func.count(TunnelEvent.id))
                       .where(TunnelEvent.variant_id.in_(variant_ids))) or 0
    db.execute(TunnelEvent.__table__.delete().where(TunnelEvent.variant_id.in_(variant_ids)))
    return compte


@router.post("/api/sales-funnels/{tunnel_id}/pages/{page_id}/variants", status_code=201)
def add_page_variant(tunnel_id: str, page_id: str, data: SalesVariantCreate,
                     db: Session = Depends(get_db), user: User = Depends(write_user)):
    """Ouvre une seconde version de l'etape, copie de celle en ligne.

    On part d'une copie plutot que d'une page vide : on compare deux redactions
    du meme propos, pas une page contre rien.
    """
    tunnel = owned_tunnel(tunnel_id, db, user)
    page = owned_page(tunnel, page_id)
    if len(page.variants) >= MAX_VARIANTS:
        raise HTTPException(422, f"Une étape se compare au maximum à {MAX_VARIANTS} autres versions.")
    lettre = chr(ord("B") + len(page.variants))
    variante = PageVariant(page_id=page.id, name=data.name.strip() or f"Version {lettre}", html=page.html)
    db.add(variante)
    db.commit()
    db.refresh(tunnel)
    return tunnel_payload(tunnel)


@router.delete("/api/sales-funnels/{tunnel_id}/pages/{page_id}/variants/{variant_id}")
def delete_page_variant(tunnel_id: str, page_id: str, variant_id: str,
                        db: Session = Depends(get_db), user: User = Depends(write_user)):
    tunnel = owned_tunnel(tunnel_id, db, user)
    page = owned_page(tunnel, page_id)
    variante = next((item for item in page.variants if item.id == variant_id), None)
    if not variante:
        raise HTTPException(404, "Version introuvable")
    mesures = drop_variant_events(db, [variante.id])
    db.delete(variante)
    db.commit()
    db.refresh(tunnel)
    return {"tunnel": tunnel_payload(tunnel),
            "warnings": [f"{mesures} mesures de cette version ont été supprimées avec elle."] if mesures else []}


@router.post("/api/sales-funnels/{tunnel_id}/pages/{page_id}/variants/{variant_id}/promote")
def promote_page_variant(tunnel_id: str, page_id: str, variant_id: str,
                         db: Session = Depends(get_db), user: User = Depends(write_user)):
    """La version retenue devient l'etape, et la comparaison se termine.

    Le document precedent part en version precedente : on peut y revenir.
    """
    tunnel = owned_tunnel(tunnel_id, db, user)
    page = owned_page(tunnel, page_id)
    variante = next((item for item in page.variants if item.id == variant_id), None)
    if not variante:
        raise HTTPException(404, "Version introuvable")
    db.add(PageVersion(page_id=page.id, html=page.html))
    page.html = variante.html
    page.draft_html = None
    mesures = drop_variant_events(db, [item.id for item in page.variants])
    for item in list(page.variants):
        db.delete(item)
    db.commit()
    db.refresh(tunnel)
    return {"tunnel": tunnel_payload(tunnel),
            "warnings": [f"La comparaison est terminée : {mesures} mesures des versions comparées "
                         "ont été supprimées."] if mesures else []}


@router.post("/api/sales-funnels/{tunnel_id}/publish")
def publish_sales_funnel(tunnel_id: str, db: Session = Depends(get_db), user: User = Depends(write_user)):
    tunnel = owned_tunnel(tunnel_id, db, user)
    for page in tunnel.pages:
        if page.draft_html:
            db.add(PageVersion(page_id=page.id, html=page.html))
            page.html = page.draft_html
            page.draft_html = None
        for variante in page.variants:
            if variante.draft_html:
                variante.html = variante.draft_html
                variante.draft_html = None
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
    if not pages:
        raise HTTPException(422, "Ce parcours ne peut pas encore être exporté.")
    # Noms prévisibles et sans collision : le nom d'une étape est libre et peut
    # se répéter, sa place non.
    names = ["index.html", *(f"{page.slug or f'etape-{index + 2}'}.html"
                             for index, page in enumerate(pages[1:]))]
    destination = json.dumps(tunnel.goal_url).replace("<", "\u003c")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for index, (page, filename) in enumerate(zip(pages, names, strict=True)):
            # Le serveur n'est plus là : la chaîne réelle est recopiée en dur.
            jumps = [f"if(event.target.closest('[data-sillage-goal]')){{location.href={destination}}}"]
            if index + 1 < len(names):
                following = json.dumps(names[index + 1])
                jumps.insert(0, f"if(event.target.closest('[data-sillage-next]')){{location.href={following}}}")
            script = "<script>document.addEventListener('click',function(event){" + "".join(jumps) + "})</script>"
            output.writestr(filename, page.html.replace("</body>", script + "</body>", 1))
        sommaire = "\n".join(f"  {filename} - {page.name}" for page, filename in zip(pages, names, strict=True))
        output.writestr("LISEZ-MOI.txt", "Ce dossier contient une copie HTML du tunnel publié.\n"
                        "Ouvrez index.html pour commencer. Le bouton final mène à l'adresse externe configurée.\n\n"
                        f"Les étapes, dans l'ordre :\n{sommaire}\n\n"
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
    # Par version : ce que chacune a recu, et ce qu'elle a rapporte au bout.
    par_version = db.execute(
        select(TunnelEvent.page_id, TunnelEvent.variant_id, TunnelEvent.kind, func.count(TunnelEvent.id))
        .where(TunnelEvent.tunnel_id == tunnel.id, TunnelEvent.created_at >= since)
        .group_by(TunnelEvent.page_id, TunnelEvent.variant_id, TunnelEvent.kind)).all()
    vus = {(page_id, variant, kind): count for page_id, variant, kind, count in par_version}
    # Le clic final arrive souvent plusieurs etapes plus loin : on le rattache a
    # la version vue, en passant par la session.
    vues = (select(TunnelEvent.session_id, TunnelEvent.page_id, TunnelEvent.variant_id)
            .where(TunnelEvent.tunnel_id == tunnel.id, TunnelEvent.kind == "page_view",
                   TunnelEvent.created_at >= since).subquery())
    aboutis = (select(TunnelEvent.session_id)
               .where(TunnelEvent.tunnel_id == tunnel.id, TunnelEvent.kind == "goal_click",
                      TunnelEvent.created_at >= since).distinct().subquery())
    buts = {(page_id, variant): count for page_id, variant, count in db.execute(
        select(vues.c.page_id, vues.c.variant_id, func.count(func.distinct(vues.c.session_id)))
        .join(aboutis, aboutis.c.session_id == vues.c.session_id)
        .group_by(vues.c.page_id, vues.c.variant_id)).all()}

    def versions_de(page: Page) -> list[dict]:
        if not page.variants:
            return []
        lignes = [("", "Version A (témoin)")] + [(item.id, item.name) for item in page.variants]

        def chiffres(identifiant: str) -> tuple[int, int]:
            return (vus.get((page.id, identifiant, "page_view"), 0), buts.get((page.id, identifiant), 0))

        temoin = chiffres("")
        resultat = []
        for identifiant, nom in lignes:
            visites, aboutis_ = chiffres(identifiant)
            resultat.append({
                "id": identifiant, "name": nom, "visits": visites,
                "actions": (vus.get((page.id, identifiant, "step_click"), 0)
                            + vus.get((page.id, identifiant, "goal_click"), 0)),
                "goals": aboutis_,
                "conversion": round(aboutis_ / visites * 100, 1) if visites else None,
                # Le temoin ne se compare pas a lui-meme.
                "verdict": None if not identifiant else compare_versions(temoin, (visites, aboutis_)),
            })
        return resultat

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
            "pages": [{"id": page.id, "name": page.name, "variants": versions_de(page),
                       "visits": counts.get((page.id, "page_view"), 0),
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
                        secure=request.url.scheme == "https", samesite="lax", path="/")


def record_event(db: Session, tunnel: Tunnel, page: Page, sid: str, kind: str, source: str,
                 variant_id: str = "") -> bool:
    # La cle de deduplication ignore la version : une session ne voit qu'une
    # seule version d'une etape, et ne doit compter qu'une fois.
    values = {"id": str(uuid4()), "tunnel_id": tunnel.id, "page_id": page.id,
              "session_id": sid, "event_key": f"{sid}:{page.id}:{kind}", "kind": kind,
              "variant_id": variant_id, "source": source}
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
            page.visits = Page.visits + 1
        elif kind in {"step_click", "goal_click"}:
            page.conversions = Page.conversions + 1
    return inserted


def step_slug(db: Session, name: str) -> str:
    """Une adresse lisible pour une etape, unique parmi toutes les pages."""
    pris = {slug for slug in db.scalars(select(Page.slug).where(Page.slug.is_not(None)))}
    return free_slug(name, pris | RESERVED_SLUGS)


def step_path(tunnel: Tunnel, page: Page, index: int) -> str:
    """L'adresse publique d'une etape. La premiere est la racine du tunnel."""
    return f"/t/{tunnel.slug}" if index == 0 else f"/t/{tunnel.slug}/{page.slug}"


def assigned_variant(page: Page, journey_variants: dict) -> tuple[str, str]:
    """La version montree a cette session, tiree une fois puis tenue.

    Un visiteur qui verrait A puis B ne mesurerait rien : le tirage est donc
    fige dans le cookie de parcours des la premiere vue. Une variante
    supprimee entre-temps ramene au temoin.
    """
    choix = journey_variants.get(page.id)
    vivantes = {variante.id: variante for variante in page.variants}
    if choix is None or (choix and choix not in vivantes):
        choix = random.choice(["", *sorted(vivantes)])
    return choix, (vivantes[choix].html if choix else page.html)


def document_for(db: Session, tunnel: Tunnel, step: str, request: Request,
                 response: Response, source: str) -> str:
    """Rend une etape et enregistre le passage.

    Arriver ici depuis l'etape precedente vaut clic sur son bouton : sans page
    parente pour l'intercepter, c'est la navigation elle-meme qui le dit.
    """
    pages = sorted(tunnel.pages, key=lambda item: item.position)
    if not pages:
        raise HTTPException(404, "Étape introuvable")
    index = 0 if not step else next((i for i, item in enumerate(pages) if item.slug == step), -1)
    if index < 0:
        raise HTTPException(404, "Étape introuvable")
    page = pages[index]
    precedent = journey(request, tunnel)
    sid = precedent.get("sid") if precedent and precedent.get("sid") else str(uuid4())
    source = (precedent.get("source") if precedent else None) or source
    versions = dict(precedent.get("variants") or {}) if precedent else {}
    if precedent and index > 0:
        venant = next((item for item in pages if item.id == precedent.get("page")), None)
        if venant and venant.next_page_id == page.id:
            record_event(db, tunnel, venant, sid, "step_click", source, versions.get(venant.id, ""))
    version, html = assigned_variant(page, versions)
    versions[page.id] = version
    record_event(db, tunnel, page, sid, "page_view", source, version)
    db.commit()
    set_journey(response, request, {"tunnel": tunnel.id, "sid": sid, "page": page.id,
                                    "source": source, "variants": versions})
    reference = tunnel_seo(tunnel)
    suivante = pages[index + 1] if index + 1 < len(pages) and page.next_page_id else None
    return public_document(
        html,
        title=reference["title"], description=reference["description"],
        canonical=f"{settings.site_url}{step_path(tunnel, page, index)}",
        next_url=step_path(tunnel, suivante, index + 1) if suivante else None,
        goal_url=f"/t/{tunnel.slug}/go" if tunnel.goal_url else None,
    )


@router.get("/api/public/sales/{slug}/document", response_class=HTMLResponse)
def sales_document(slug: str, request: Request, response: Response, step: str = Query(default="", max_length=160),
                   source: str = Query(default="Lien direct", max_length=80), db: Session = Depends(get_db)):
    """Le document d'une etape, servi tel quel : c'est la page que lit le visiteur."""
    rate_limit("sales-journey", client_ip(request), limit=JOURNEY_CALLS, window_seconds=JOURNEY_WINDOW)
    tunnel = live_tunnel(slug, db)
    html = document_for(db, tunnel, step.strip(), request, response, source.strip()[:80] or "Lien direct")
    response.headers["Cache-Control"] = "no-store"
    return HTMLResponse(html, headers=dict(response.headers))


@router.get("/api/public/sales/{slug}/go")
def sales_goal_redirect(slug: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """Enregistre le clic final puis renvoie le visiteur vers l'adresse externe."""
    rate_limit("sales-journey", client_ip(request), limit=JOURNEY_CALLS, window_seconds=JOURNEY_WINDOW)
    tunnel = live_tunnel(slug, db)
    current = journey(request, tunnel)
    page = db.get(Page, current.get("page")) if current else None
    if not page or page.tunnel_id != tunnel.id or not tunnel.goal_url or not current.get("sid"):
        raise HTTPException(403, "Action inaccessible")
    versions = current.get("variants") or {}
    record_event(db, tunnel, page, current["sid"], "goal_click",
                 current.get("source") or "Lien direct", versions.get(page.id, ""))
    db.commit()
    return RedirectResponse(tunnel.goal_url, status_code=303, headers={"Cache-Control": "no-store"})
