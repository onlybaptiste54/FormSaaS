"""Formulaires, tunnels de pages, retouches de Luna, versions et brouillons."""

import json
import logging
from html import escape

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import cast, desc, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, get_db
from .brand_site import SiteError, proxy_path, read_site, site_name
from .luna import LunaAPIError, analyze_site_brand, default_content, default_design, generate_campaign, generate_page, merge_page_region, revise_page, slugify, stream_page_revision
from .luna_ops import contrast_ratio
from .models import Company, Form, FormResponse, FormVersion, Page, Tunnel, User, initial_tunnel_id, thanks_page_id, uid
from .page_document import blank_form_html, free_slug, legacy_to_html, prepare_page, render_page, same_document
from .schemas import DraftUpdate, FormCreate, FormUpdate, LunaRefineRequest, TunnelPageCreate, TunnelPageUpdate
from .security import current_user, write_user
from .inbox import csv_response, response_json
from .account import luna_identity
from .campaigns import owned_campaign


router = APIRouter()


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


def unique_slug(db: Session, name: str) -> str:
    """Deux campagnes peuvent avoir un formulaire du meme nom : le lien doit rester unique."""
    base = slugify(name)
    candidate = base
    suffix = 2
    while db.scalar(select(Form.id).where(Form.slug == candidate)):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


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


def creation_identity(source: str, website_url: str, company: Company) -> dict:
    """L'identite que la page appliquera, selon ce que l'utilisateur a choisi.

    La charte d'un client est lue sur son site et remplace celle du compte :
    une page faite pour un tiers ne doit rien porter de la marque qui la
    commande. Le dictionnaire vide est un choix, pas une absence de reponse.
    """
    if source == "none":
        return {}
    if source != "site":
        return luna_identity(company)
    if not website_url.strip():
        raise HTTPException(422, "Indiquez l'adresse du site dont il faut reprendre la charte.")
    facts = read_site(website_url)
    nom = site_name(facts)
    profile = analyze_site_brand(
        facts,
        {"name": nom},
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    identite = {"name": nom, "tone": profile["tone"], "brand": profile}
    # L'accent calcule sur le site vaut mieux que le premier element de la
    # palette, qui est presque toujours un blanc ou un noir de structure.
    if accent := facts.get("accent"):
        identite["accent_color"] = accent
    # Les roles disent quoi faire de chaque teinte : sans eux, « c'est trop
    # blanc » ne menait a rien, faute de savoir laquelle pose un fond doux.
    if roles := {cle: valeur for cle, valeur in (facts.get("roles") or {}).items() if valeur}:
        identite["couleurs"] = roles
    # Les visuels voyagent avec l'identite : Luna les retrouve a chaque retouche,
    # et le serveur refuse toute image qui n'en vient pas.
    if visuels := facts.get("images"):
        # Les visuels passent par Sillage : une image d'une autre origine
        # souille le canvas de la capture de zone, qui echoue alors en silence.
        identite["images"] = [{**visuel, "source": visuel["url"],
                               "url": proxy_path(visuel["url"], settings.secret_key)}
                              for visuel in visuels]
    return identite


def page_identity(form: Form) -> dict:
    """L'identite que cette page applique, figee a sa creation.

    NULL signale un formulaire cree avant que l'identite ne soit figee : il
    retombe sur celle du compte. Un dictionnaire vide est un choix explicite de
    n'appliquer aucune identite, et doit le rester.
    """
    if form.identity is not None:
        return form.identity
    return luna_identity(form.campaign.company)


def owned_form(form_id: str, db: Session, user: User) -> Form:
    form = db.get(Form, form_id)
    if not form or form.campaign.company_id != user.company_id:
        raise HTTPException(404, "Formulaire introuvable")
    return form


@router.get("/api/campaigns/{campaign_id}/forms")
def list_forms(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaign = owned_campaign(campaign_id, db, user)
    forms = db.scalars(select(Form).where(Form.campaign_id == campaign.id).order_by(desc(Form.updated_at))).all()
    return [form_json(db, f) for f in forms]


@router.post("/api/campaigns/{campaign_id}/forms", status_code=201)
def create_form(campaign_id: str, data: FormCreate, db: Session = Depends(get_db), user: User = Depends(write_user)):
    campaign = owned_campaign(campaign_id, db, user)
    # brand_source absent : les anciens appels passent encore par use_brand.
    source = data.brand_source or ("company" if data.use_brand else "none")
    try:
        identity = creation_identity(source, data.website_url, user.company)
    except SiteError as exc:
        raise HTTPException(422, str(exc)) from exc
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Ce site n'a pas répondu.") from exc
    try:
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


@router.get("/api/forms/{form_id}")
def get_form(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return form_json(db, owned_form(form_id, db, user))


@router.patch("/api/forms/{form_id}")
def update_form(form_id: str, data: FormUpdate, db: Session = Depends(get_db), user: User = Depends(write_user)):
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
    query = select(Page.slug).where(Page.slug.is_not(None))
    if exclude_page_id:
        query = query.where(Page.id != exclude_page_id)
    return free_slug(name, {slug for slug in db.scalars(query)})


@router.get("/api/forms/{form_id}/tunnel")
def get_form_tunnel(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    return tunnel_json(form_tunnel(db, form), form)


@router.post("/api/forms/{form_id}/tunnel/pages", status_code=201)
def create_tunnel_page(form_id: str, data: TunnelPageCreate, db: Session = Depends(get_db), user: User = Depends(write_user)):
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


@router.patch("/api/forms/{form_id}/tunnel/pages/{page_id}")
def update_tunnel_page(form_id: str, page_id: str, data: TunnelPageUpdate, db: Session = Depends(get_db), user: User = Depends(write_user)):
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

    # Luna a repondu sans modifier la page : rien a enregistrer, et surtout pas
    # une version qui laisserait croire a un changement.
    if not revision["html"].strip():
        return {"message": revision["message"], "form": form_json(db, form),
                "version": None, "touched": [], "changed": False}
    try:
        candidate = merge_page_region(expected_html, revision["html"], revision.get("region"))
        cleaned_html, manifest = prepare_page(candidate, require_form=page.role == "form")
    except ValueError:
        db.rollback()
        raise

    # Reponse qui n'a rien change : la reserialisation du CSS suffit a rendre
    # les chaines differentes, alors on compare au bruit pres. Sans cela, Luna
    # annonce un changement, une version s'empile, et l'utilisateur voit une
    # page identique avec un bouton « annuler cette modification ».
    if same_document(cleaned_html, expected_html):
        db.rollback()
        return {"message": "Je n'ai rien changé à la page : reformulez en précisant ce qui doit bouger.",
                "form": form_json(db, form), "version": None, "touched": [], "changed": False}

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
        "changed": True,
    }


@router.post("/api/forms/{form_id}/luna/refine")
def refine_with_luna(form_id: str, data: LunaRefineRequest, db: Session = Depends(get_db), user: User = Depends(write_user)):
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


@router.post("/api/forms/{form_id}/luna/refine/stream")
def refine_with_luna_stream(form_id: str, data: LunaRefineRequest, db: Session = Depends(get_db), user: User = Depends(write_user)):
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


@router.get("/api/forms/{form_id}/versions")
def list_versions(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    return [version_json(version) for version in form.versions]


@router.patch("/api/forms/{form_id}/draft")
def update_draft(form_id: str, data: DraftUpdate, db: Session = Depends(get_db), user: User = Depends(write_user)):
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


@router.post("/api/forms/{form_id}/draft/publish")
def publish_draft(form_id: str, db: Session = Depends(get_db), user: User = Depends(write_user)):
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


@router.post("/api/forms/{form_id}/draft/discard")
def discard_draft(form_id: str, db: Session = Depends(get_db), user: User = Depends(write_user)):
    form = owned_form(form_id, db, user)
    form.draft = None
    for page in form_tunnel(db, form).pages:
        page.draft_html = None
        page.draft_manifest = None
    db.commit()
    db.refresh(form)
    return form_json(db, form)


@router.post("/api/forms/{form_id}/versions/{version_id}/restore")
def restore_version(form_id: str, version_id: str, db: Session = Depends(get_db), user: User = Depends(write_user)):
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


@router.post("/api/forms/{form_id}/duplicate", status_code=201)
def duplicate_form(form_id: str, db: Session = Depends(get_db), user: User = Depends(write_user)):
    source = owned_form(form_id, db, user)
    name = f"{source.name} - copie"
    copy = Form(campaign_id=source.campaign_id, creator_id=user.id, identity=page_identity(source), name=name, slug=unique_slug(db, name), description=source.description, kind=source.kind, fields=source.fields, design=source.design or default_design(), content=source.content or default_content(source.kind), thank_you=thank_you_settings(source), visibility="private")
    db.add(copy)
    copy_form_pages(db, source, copy)
    db.commit()
    db.refresh(copy)
    return form_json(db, copy)


@router.get("/api/forms/{form_id}/responses")
def form_responses(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    rows = db.scalars(select(FormResponse).where(FormResponse.form_id == form.id).order_by(desc(FormResponse.created_at))).all()
    return [response_json(r) for r in rows]


@router.get("/api/forms/{form_id}/export.csv")
def export_form_csv(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    rows = db.scalars(select(FormResponse).where(FormResponse.form_id == form.id)).all()
    return csv_response(rows, f"{form.slug}.csv")
