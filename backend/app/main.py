import csv
import io
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, get_db, initialize_schema
from .luna import LunaAPIError, analyze_brand, default_content, default_design, generate_campaign, revise_campaign, slugify
from .models import Campaign, CampaignVersion, Company, FormResponse, Template, User
from .schemas import BrandAnalyzeRequest, CampaignCreate, CampaignUpdate, CompanyUpdate, DraftUpdate, LoginIn, LunaRefineRequest, SubmitResponse
from .security import create_token, current_user, verify_password
from .seed import seed
from .template_catalog import CURATED_TEMPLATES, campaign_fields, curated_template, template_kind, template_payload


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_schema()
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="Sillage API", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


EDITABLE_KEYS = ("name", "description", "fields", "design", "content", "thank_you")

# Nombre de versions conservees par campagne.
VERSION_LIMIT = 30


def published_state(c: Campaign) -> dict:
    """Etat en ligne du formulaire : ce que voit un visiteur."""
    return {
        "name": c.name,
        "description": c.description,
        "fields": c.fields,
        "design": c.design or default_design(),
        "content": c.content or default_content(c.kind),
        "thank_you": c.thank_you,
    }


def editing_state(c: Campaign) -> dict:
    """Etat en cours d'edition : le brouillon s'il existe, sinon le publie."""
    return {**published_state(c), **(c.draft or {})}


def record_version(db: Session, campaign: Campaign, snapshot: dict, *, source: str, instruction: str = "", message: str = "") -> CampaignVersion:
    version = CampaignVersion(campaign_id=campaign.id, snapshot=snapshot, source=source, instruction=instruction, message=message)
    db.add(version)
    db.flush()
    extra = db.scalars(
        select(CampaignVersion).where(CampaignVersion.campaign_id == campaign.id).order_by(desc(CampaignVersion.created_at)).offset(VERSION_LIMIT)
    ).all()
    for old in extra:
        db.delete(old)
    return version


def version_json(version: CampaignVersion):
    return {"id": version.id, "source": version.source, "instruction": version.instruction, "message": version.message, "created_at": version.created_at.isoformat()}


def campaign_json(c: Campaign):
    responses = len(c.responses)
    return {"id": c.id, "name": c.name, "slug": c.slug, "description": c.description, "kind": c.kind, "status": c.status, "visibility": c.visibility, "fields": c.fields, "design": c.design or default_design(), "content": c.content or default_content(c.kind), "thank_you": c.thank_you, "draft": c.draft, "visits": c.visits, "responses": responses, "conversion": round((responses / c.visits * 100) if c.visits else 0, 1), "archived": c.archived, "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat()}


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


def campaign_from_template(template: dict, user: User) -> Campaign:
    kind = template_kind(template.get("category", "Contact"))
    return Campaign(
        company_id=user.company_id,
        creator_id=user.id,
        name=template["name"],
        slug=slugify(template["name"]),
        description=template["description"],
        kind=kind,
        status="draft",
        visibility="private",
        fields=campaign_fields(template["fields"], user.company.name),
        design=template.get("design") or default_design(),
        content=default_content(kind),
        thank_you=template.get("thank_you") or template_payload(template)["thank_you"],
    )


def luna_history(campaign: Campaign) -> list[dict]:
    """Derniers echanges, pour que Luna se souvienne de la conversation."""
    turns = []
    for version in campaign.versions[-6:]:
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
    campaigns = db.scalars(select(Campaign).where(Campaign.company_id == user.company_id, Campaign.archived.is_(False))).all()
    ids = [c.id for c in campaigns]
    total = db.scalar(select(func.count(FormResponse.id)).where(FormResponse.campaign_id.in_(ids))) if ids else 0
    since = datetime.now(timezone.utc) - timedelta(days=7)
    week = db.scalar(select(func.count(FormResponse.id)).where(FormResponse.campaign_id.in_(ids), FormResponse.created_at >= since)) if ids else 0
    daily = []
    for offset in range(6, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=offset)).date()
        count = db.scalar(select(func.count(FormResponse.id)).where(FormResponse.campaign_id.in_(ids), func.date(FormResponse.created_at) == day)) if ids else 0
        daily.append({"date": day.isoformat(), "count": count or 0})
    visits = sum(c.visits for c in campaigns)
    sources = db.execute(select(FormResponse.source, func.count(FormResponse.id)).where(FormResponse.campaign_id.in_(ids)).group_by(FormResponse.source).order_by(desc(func.count(FormResponse.id)))) if ids else []
    recent = db.scalars(select(FormResponse).where(FormResponse.campaign_id.in_(ids)).order_by(desc(FormResponse.created_at)).limit(5)).all() if ids else []
    return {"campaigns": len(campaigns), "active": sum(c.status == "active" for c in campaigns), "responses": total or 0, "week_responses": week or 0, "conversion": round((total / visits * 100) if visits else 0, 1), "daily": daily, "sources": [{"name": name, "count": count} for name, count in sources], "recent": [{"id": r.id, "campaign": r.campaign.name, "name": r.answers.get("name", "Réponse anonyme"), "source": r.source, "created_at": r.created_at.isoformat()} for r in recent]}


@app.get("/api/team")
def team(db: Session = Depends(get_db), user: User = Depends(current_user)):
    members = db.scalars(select(User).where(User.company_id == user.company_id).order_by(User.created_at)).all()
    return [{"id": m.id, "full_name": m.full_name, "email": m.email, "role": m.role} for m in members]


@app.get("/api/campaigns")
def list_campaigns(archived: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(Campaign).where(Campaign.company_id == user.company_id, Campaign.archived == archived).order_by(desc(Campaign.updated_at))
    return [campaign_json(c) for c in db.scalars(query).all()]


@app.get("/api/library")
def library(db: Session = Depends(get_db), user: User = Depends(current_user)):
    saved = db.scalars(select(Template).where(Template.company_id == user.company_id).order_by(desc(Template.updated_at))).all()
    recent = db.scalars(select(Campaign).where(Campaign.company_id == user.company_id, Campaign.archived.is_(False)).order_by(desc(Campaign.updated_at)).limit(4)).all()
    return {
        "featured": [template_payload(template) for template in CURATED_TEMPLATES],
        "saved": [saved_template_json(template) for template in saved],
        "recent": [campaign_json(campaign) for campaign in recent],
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
def use_featured_template(template_key: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = curated_template(template_key)
    if not source:
        raise HTTPException(404, "Modèle introuvable")
    campaign = campaign_from_template(template_payload(source), user)
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign_json(campaign)


@app.post("/api/library/templates/{template_id}/use", status_code=201)
def use_saved_template(template_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    template = db.get(Template, template_id)
    if not template or template.company_id != user.company_id:
        raise HTTPException(404, "Modèle introuvable")
    campaign = campaign_from_template(saved_template_json(template), user)
    template.uses += 1
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign_json(campaign)


@app.post("/api/campaigns", status_code=201)
def create_campaign(data: CampaignCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
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
    campaign = Campaign(company_id=user.company_id, creator_id=user.id, brief={"prompt": data.prompt, "context": data.context}, **generated)
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign_json(campaign)


def owned_campaign(campaign_id: str, db: Session, user: User) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.company_id != user.company_id:
        raise HTTPException(404, "Campagne introuvable")
    return campaign


@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return campaign_json(owned_campaign(campaign_id, db, user))


@app.patch("/api/campaigns/{campaign_id}")
def update_campaign(campaign_id: str, data: CampaignUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaign = owned_campaign(campaign_id, db, user)
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(campaign, key, value)
    db.commit()
    return campaign_json(campaign)


@app.post("/api/campaigns/{campaign_id}/luna/refine")
def refine_with_luna(campaign_id: str, data: LunaRefineRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not settings.openai_api_key:
        raise HTTPException(503, "Ajoutez OPENAI_API_KEY dans votre fichier .env pour modifier le design avec Luna.")
    campaign = owned_campaign(campaign_id, db, user)
    state = editing_state(campaign)
    try:
        revision = revise_campaign(
            {**state, "kind": campaign.kind, "brief": campaign.brief or {}},
            data.instruction,
            luna_identity(user.company),
            selection={
                "element_ids": data.element_ids,
                "label": data.selection_label,
                "view": data.view,
            },
            history=luna_history(campaign),
            screenshot_data_url=data.screenshot_data_url,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
        )
    except LunaAPIError as exc:
        raise HTTPException(503, str(exc)) from exc

    if campaign.draft is None and not campaign.versions:
        record_version(db, campaign, published_state(campaign), source="initial", message="Version publiée")
    campaign.draft = {key: revision[key] for key in EDITABLE_KEYS}
    version = record_version(db, campaign, campaign.draft, source="luna", instruction=data.instruction, message=revision["assistant_message"])
    db.commit()
    db.refresh(campaign)
    return {
        "message": revision["assistant_message"],
        "campaign": campaign_json(campaign),
        "version": version_json(version),
        "touched": revision["touched"],
        "ops": revision["ops"],
    }


@app.get("/api/campaigns/{campaign_id}/versions")
def list_versions(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaign = owned_campaign(campaign_id, db, user)
    return [version_json(version) for version in campaign.versions]


@app.patch("/api/campaigns/{campaign_id}/draft")
def update_draft(campaign_id: str, data: DraftUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Edition directe : ce qui est corrige a la main va aussi dans le brouillon."""
    campaign = owned_campaign(campaign_id, db, user)
    changes = data.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(422, "Aucune modification transmise")
    if campaign.draft is None and not campaign.versions:
        record_version(db, campaign, published_state(campaign), source="initial", message="Version publiée")
    campaign.draft = {**editing_state(campaign), **changes}
    record_version(db, campaign, campaign.draft, source="manual", message="Modification manuelle")
    db.commit()
    db.refresh(campaign)
    return campaign_json(campaign)


@app.post("/api/campaigns/{campaign_id}/draft/publish")
def publish_draft(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaign = owned_campaign(campaign_id, db, user)
    if not campaign.draft:
        raise HTTPException(422, "Aucune modification à publier")
    for key, value in campaign.draft.items():
        if key in EDITABLE_KEYS:
            setattr(campaign, key, value)
    campaign.draft = None
    record_version(db, campaign, published_state(campaign), source="publish", message="Modifications publiées")
    db.commit()
    db.refresh(campaign)
    return campaign_json(campaign)


@app.post("/api/campaigns/{campaign_id}/draft/discard")
def discard_draft(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaign = owned_campaign(campaign_id, db, user)
    campaign.draft = None
    db.commit()
    db.refresh(campaign)
    return campaign_json(campaign)


@app.post("/api/campaigns/{campaign_id}/versions/{version_id}/restore")
def restore_version(campaign_id: str, version_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Annuler, c'est revenir a une version precedente : rien n'est perdu."""
    campaign = owned_campaign(campaign_id, db, user)
    version = db.get(CampaignVersion, version_id)
    if not version or version.campaign_id != campaign.id:
        raise HTTPException(404, "Version introuvable")
    campaign.draft = {key: value for key, value in version.snapshot.items() if key in EDITABLE_KEYS}
    record_version(db, campaign, campaign.draft, source="restore", message="Retour à une version précédente")
    db.commit()
    db.refresh(campaign)
    return campaign_json(campaign)


@app.post("/api/campaigns/{campaign_id}/duplicate", status_code=201)
def duplicate_campaign(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = owned_campaign(campaign_id, db, user)
    copy = Campaign(company_id=user.company_id, creator_id=user.id, name=f"{source.name} - copie", slug=slugify(source.name), description=source.description, kind=source.kind, fields=source.fields, design=source.design or default_design(), content=source.content or default_content(source.kind), thank_you=source.thank_you, visibility="private")
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return campaign_json(copy)


@app.get("/api/campaigns/{campaign_id}/responses")
def campaign_responses(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaign = owned_campaign(campaign_id, db, user)
    rows = db.scalars(select(FormResponse).where(FormResponse.campaign_id == campaign.id).order_by(desc(FormResponse.created_at))).all()
    return [{"id": r.id, "answers": r.answers, "source": r.source, "promo_code": r.promo_code, "consent": r.consent, "created_at": r.created_at.isoformat()} for r in rows]


@app.delete("/api/responses/{response_id}", status_code=204)
def delete_response(response_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    response = db.get(FormResponse, response_id)
    if not response or response.campaign.company_id != user.company_id:
        raise HTTPException(404, "Réponse introuvable")
    db.delete(response)
    db.commit()


@app.get("/api/campaigns/{campaign_id}/export.csv")
def export_csv(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaign = owned_campaign(campaign_id, db, user)
    rows = db.scalars(select(FormResponse).where(FormResponse.campaign_id == campaign.id)).all()
    keys = list(dict.fromkeys(k for r in rows for k in r.answers.keys()))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["date", "source", "consent", *keys])
    writer.writeheader()
    for r in rows:
        writer.writerow({"date": r.created_at.isoformat(), "source": r.source, "consent": r.consent, **r.answers})
    return StreamingResponse(iter([buffer.getvalue().encode("utf-8-sig")]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{campaign.slug}.csv"'})


@app.get("/api/public/{slug}")
def public_campaign(slug: str, db: Session = Depends(get_db)):
    campaign = db.scalar(select(Campaign).where(Campaign.slug == slug, Campaign.archived.is_(False)))
    if not campaign:
        raise HTTPException(404, "Formulaire introuvable")
    c = campaign.company
    return {"name": campaign.name, "description": campaign.description, "fields": campaign.fields, "design": campaign.design or default_design(), "content": campaign.content or default_content(campaign.kind), "thank_you": campaign.thank_you, "status": campaign.status, "company": {"name": c.name, "legal_name": c.legal_name, "address": c.address, "primary_color": c.primary_color, "accent_color": c.accent_color, "dpo_email": c.dpo_email, "logo": c.logo}}


@app.post("/api/public/{slug}/visit", status_code=204)
def track_visit(slug: str, db: Session = Depends(get_db)):
    """Une visite par session, comptée par le navigateur : un GET ne doit rien écrire."""
    campaign = db.scalar(select(Campaign).where(Campaign.slug == slug, Campaign.status == "active", Campaign.archived.is_(False)))
    if campaign:
        campaign.visits += 1
        db.commit()


@app.post("/api/public/{slug}/submit", status_code=201)
def submit(slug: str, data: SubmitResponse, request: Request, db: Session = Depends(get_db)):
    campaign = db.scalar(select(Campaign).where(Campaign.slug == slug, Campaign.status == "active", Campaign.archived.is_(False)))
    if not campaign:
        raise HTTPException(404, "Ce formulaire n'accepte pas de réponse")
    required = [f for f in campaign.fields if f.get("required") and f.get("type") != "consent"]
    missing = [f["label"] for f in required if data.answers.get(f["id"]) in (None, "", [])]
    if missing:
        raise HTTPException(422, f"Champs requis : {', '.join(missing)}")
    consent_field = next((f for f in campaign.fields if f.get("type") == "consent"), None)
    if consent_field and consent_field.get("required") and not data.consent:
        raise HTTPException(422, "Le consentement est requis")
    row = FormResponse(campaign_id=campaign.id, answers=data.answers, source=data.source, promo_code=data.promo_code, consent=data.consent, consent_text=consent_field.get("label", "") if consent_field else "", ip_address=request.client.host if request.client else "", user_agent=request.headers.get("user-agent", "")[:300])
    db.add(row)
    db.commit()
    return {"id": row.id, "thank_you": campaign.thank_you}
