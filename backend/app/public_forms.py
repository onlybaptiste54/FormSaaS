"""Formulaire public : affichage, parcours et soumission."""

from uuid import uuid4
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .luna import default_content, default_design
from .models import Form, FormResponse, Page, Tunnel
from .page_document import render_page
from .schemas import PublicPageAdvance, PublicPageVisit, SubmitResponse
from .security import client_ip, rate_limit
from .forms import consent_text, form_page, form_tunnel, thank_you_settings


router = APIRouter()


# Assez large pour la tablette d'un comptoir qui enchaîne les inscriptions,
# assez serré pour qu'un script n'inonde pas la boîte de réception de faux
# consentements.
SUBMISSIONS, SUBMISSION_WINDOW = 30, 10 * 60


@router.get("/api/public/{slug}")
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


@router.post("/api/public/{slug}/visit")
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
        page.visits = Page.visits + 1
        if page.role == "form":
            form.visits = Form.visits + 1
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


@router.post("/api/public/{slug}/advance")
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
        current.conversions = Page.conversions + 1
        target.visits = Page.visits + 1
        if target.role == "form":
            form.visits = Form.visits + 1
        visited.append(target.id)
        db.commit()
    set_journey_cookie(response, request, {**journey, "page": target.id, "visited": visited})
    return public_page_json(target, form)


@router.post("/api/public/{slug}/submit", status_code=201)
def submit(slug: str, data: SubmitResponse, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit("submit", client_ip(request), limit=SUBMISSIONS, window_seconds=SUBMISSION_WINDOW)
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
    page.conversions = Page.conversions + 1
    next_page = db.get(Page, page.next_page_id) if page.next_page_id else form_page(form, "thanks")
    if next_page and next_page.tunnel_id != tunnel.id:
        raise HTTPException(422, "La page suivante est invalide")
    if next_page:
        next_page.visits = Page.visits + 1
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
