import csv
import io
import json
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import Text, cast, desc, func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, get_db, initialize_schema
from .luna import LunaAPIError, analyze_brand, default_content, default_design, generate_campaign, revise_campaign, slugify
from .luna_ops import contrast_ratio
from .models import Campaign, Company, Form, FormResponse, FormVersion, Template, User
from .schemas import BrandAnalyzeRequest, CampaignCreate, CampaignUpdate, CompanyUpdate, DraftUpdate, FormCreate, FormUpdate, LoginIn, LunaRefineRequest, SubmitResponse, TemplateUse
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


def published_state(f: Form) -> dict:
    """Etat en ligne du formulaire : ce que voit un visiteur."""
    return {
        "name": f.name,
        "description": f.description,
        "fields": f.fields,
        "design": f.design or default_design(),
        "content": f.content or default_content(f.kind),
        "thank_you": f.thank_you,
    }


def editing_state(f: Form) -> dict:
    """Etat en cours d'edition : le brouillon s'il existe, sinon le publie."""
    return {**published_state(f), **(f.draft or {})}


def record_version(db: Session, form: Form, snapshot: dict, *, source: str, instruction: str = "", message: str = "") -> FormVersion:
    version = FormVersion(form_id=form.id, snapshot=snapshot, source=source, instruction=instruction, message=message)
    db.add(version)
    db.flush()
    extra = db.scalars(
        select(FormVersion).where(FormVersion.form_id == form.id).order_by(desc(FormVersion.created_at)).offset(VERSION_LIMIT)
    ).all()
    for old in extra:
        db.delete(old)
    return version


def version_json(version: FormVersion):
    return {"id": version.id, "source": version.source, "instruction": version.instruction, "message": version.message, "created_at": version.created_at.isoformat()}


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
        "thank_you": f.thank_you,
        "draft": f.draft,
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


def saved_template_json(template: Template):
    return {
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
    for version in form.versions[-6:]:
        if version.instruction:
            turns.append({"role": "user", "text": version.instruction})
        if version.message and version.source == "luna":
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
        identity = luna_identity(user.company)
        if not data.use_brand:
            identity = {**identity, "brand": {}}
        generated = generate_campaign(
            data.prompt,
            identity,
            context=data.context,
            images=data.images,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
        )
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc
    # Le nom et la description saisis par l'utilisateur priment sur ceux de Luna.
    if data.name.strip():
        generated["name"] = data.name.strip()
    if data.description.strip():
        generated["description"] = data.description.strip()
    generated["slug"] = unique_slug(db, generated["name"])
    form = Form(campaign_id=campaign.id, creator_id=user.id, brief={"prompt": data.prompt, "context": data.context}, **generated)
    db.add(form)
    db.commit()
    db.refresh(form)
    return form_json(db, form)


@app.get("/api/forms/{form_id}")
def get_form(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return form_json(db, owned_form(form_id, db, user))


@app.patch("/api/forms/{form_id}")
def update_form(form_id: str, data: FormUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(form, key, value)
    db.commit()
    return form_json(db, form)


@app.post("/api/forms/{form_id}/luna/refine")
def refine_with_luna(form_id: str, data: LunaRefineRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not settings.openai_api_key:
        raise HTTPException(503, "Ajoutez OPENAI_API_KEY dans votre fichier .env pour modifier le design avec Luna.")
    form = owned_form(form_id, db, user)
    state = editing_state(form)
    try:
        revision = revise_campaign(
            {**state, "kind": form.kind, "brief": form.brief or {}},
            data.instruction,
            luna_identity(user.company),
            selection={
                "element_ids": data.element_ids,
                "label": data.selection_label,
                "view": data.view,
            },
            history=luna_history(form),
            screenshot_data_url=data.screenshot_data_url,
            images=data.images,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
        )
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc

    if form.draft is None and not form.versions:
        record_version(db, form, published_state(form), source="initial", message="Version publiée")
    form.draft = {key: revision[key] for key in EDITABLE_KEYS}
    version = record_version(db, form, form.draft, source="luna", instruction=data.instruction, message=revision["assistant_message"])
    db.commit()
    db.refresh(form)
    return {
        "message": revision["assistant_message"],
        "form": form_json(db, form),
        "version": version_json(version),
        "touched": revision["touched"],
        "ops": revision["ops"],
    }


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
        record_version(db, form, published_state(form), source="initial", message="Version publiée")
    form.draft = {**editing_state(form), **changes}
    record_version(db, form, form.draft, source="manual", message="Modification manuelle")
    db.commit()
    db.refresh(form)
    return form_json(db, form)


@app.post("/api/forms/{form_id}/draft/publish")
def publish_draft(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    if not form.draft:
        raise HTTPException(422, "Aucune modification à publier")
    for key, value in form.draft.items():
        if key in EDITABLE_KEYS:
            setattr(form, key, value)
    form.draft = None
    record_version(db, form, published_state(form), source="publish", message="Modifications publiées")
    db.commit()
    db.refresh(form)
    return form_json(db, form)


@app.post("/api/forms/{form_id}/draft/discard")
def discard_draft(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = owned_form(form_id, db, user)
    form.draft = None
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
    record_version(db, form, form.draft, source="restore", message="Retour à une version précédente")
    db.commit()
    db.refresh(form)
    return form_json(db, form)


@app.post("/api/forms/{form_id}/duplicate", status_code=201)
def duplicate_form(form_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = owned_form(form_id, db, user)
    name = f"{source.name} - copie"
    copy = Form(campaign_id=source.campaign_id, creator_id=user.id, name=name, slug=unique_slug(db, name), description=source.description, kind=source.kind, fields=source.fields, design=source.design or default_design(), content=source.content or default_content(source.kind), thank_you=source.thank_you, visibility="private")
    db.add(copy)
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
        "featured": [template_payload(template) for template in CURATED_TEMPLATES],
        "saved": [saved_template_json(template) for template in saved],
        "recent": [form_json(db, form) for form in recent],
    }


@app.post("/api/library/featured/{template_key}/save", status_code=201)
def save_featured_template(template_key: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = curated_template(template_key)
    if not source:
        raise HTTPException(404, "Modèle introuvable")
    existing = db.scalar(select(Template).where(Template.company_id == user.company_id, Template.source_key == template_key))
    if existing:
        return saved_template_json(existing)
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
    return saved_template_json(saved)


@app.post("/api/library/featured/{template_key}/use", status_code=201)
def use_featured_template(template_key: str, data: TemplateUse, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = curated_template(template_key)
    if not source:
        raise HTTPException(404, "Modèle introuvable")
    campaign = owned_campaign(data.campaign_id, db, user)
    form = form_from_template(db, template_payload(source), user, campaign)
    db.add(form)
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
def public_form(slug: str, db: Session = Depends(get_db)):
    form = db.scalar(select(Form).where(Form.slug == slug, Form.archived.is_(False)))
    if not form or form.campaign.archived:
        raise HTTPException(404, "Formulaire introuvable")
    c = form.campaign.company
    return {"name": form.name, "description": form.description, "fields": form.fields, "design": form.design or default_design(), "content": form.content or default_content(form.kind), "thank_you": form.thank_you, "status": form.status, "company": {"name": c.name, "legal_name": c.legal_name, "address": c.address, "primary_color": c.primary_color, "accent_color": c.accent_color, "dpo_email": c.dpo_email, "logo": c.logo}}


def live_form(slug: str, db: Session) -> Form | None:
    form = db.scalar(select(Form).where(Form.slug == slug, Form.status == "active", Form.archived.is_(False)))
    return form if form and not form.campaign.archived else None


@app.post("/api/public/{slug}/visit", status_code=204)
def track_visit(slug: str, db: Session = Depends(get_db)):
    """Une visite par session, comptée par le navigateur : un GET ne doit rien écrire."""
    form = live_form(slug, db)
    if form:
        form.visits += 1
        db.commit()


@app.post("/api/public/{slug}/submit", status_code=201)
def submit(slug: str, data: SubmitResponse, request: Request, db: Session = Depends(get_db)):
    form = live_form(slug, db)
    if not form:
        raise HTTPException(404, "Ce formulaire n'accepte pas de réponse")
    required = [f for f in form.fields if f.get("required") and f.get("type") != "consent"]
    missing = [f["label"] for f in required if data.answers.get(f["id"]) in (None, "", [])]
    if missing:
        raise HTTPException(422, f"Champs requis : {', '.join(missing)}")
    consent_field = next((f for f in form.fields if f.get("type") == "consent"), None)
    if consent_field and consent_field.get("required") and not data.consent:
        raise HTTPException(422, "Le consentement est requis")
    row = FormResponse(form_id=form.id, answers=data.answers, source=data.source, promo_code=data.promo_code, consent=data.consent, consent_text=consent_field.get("label", "") if consent_field else "", ip_address=request.client.host if request.client else "", user_agent=request.headers.get("user-agent", "")[:300])
    db.add(row)
    db.commit()
    return {"id": row.id, "thank_you": form.thank_you}
