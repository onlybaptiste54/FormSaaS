"""Bibliotheque de modeles : modeles vedettes et modeles enregistres."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .database import get_db
from .luna import default_content, default_design
from .models import Campaign, Company, Form, Template, User
from .page_document import legacy_to_html, prepare_page, render_page
from .schemas import TemplateUse
from .security import current_user, write_user
from .template_catalog import CURATED_TEMPLATES, campaign_fields, curated_template, template_kind, template_payload
from .forms import create_form_pages, form_json, unique_slug
from .account import luna_identity
from .campaigns import owned_campaign


router = APIRouter()


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


@router.get("/api/library")
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


@router.post("/api/library/featured/{template_key}/save", status_code=201)
def save_featured_template(template_key: str, db: Session = Depends(get_db), user: User = Depends(write_user)):
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


@router.post("/api/library/featured/{template_key}/use", status_code=201)
def use_featured_template(template_key: str, data: TemplateUse, db: Session = Depends(get_db), user: User = Depends(write_user)):
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


@router.post("/api/library/templates/{template_id}/use", status_code=201)
def use_saved_template(template_id: str, data: TemplateUse, db: Session = Depends(get_db), user: User = Depends(write_user)):
    template = db.get(Template, template_id)
    if not template or template.company_id != user.company_id:
        raise HTTPException(404, "Modèle introuvable")
    campaign = owned_campaign(data.campaign_id, db, user)
    form = form_from_template(db, saved_template_json(template), user, campaign)
    template.uses = Template.uses + 1
    db.add(form)
    create_form_pages(db, form)
    db.commit()
    db.refresh(form)
    return form_json(db, form)
