"""Connexion, compte, marque de l'entreprise, statistiques et equipe."""

import hmac
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .brand_site import SiteError, fetch_image, read_site, sign_image
from .luna import LunaAPIError, analyze_brand, analyze_site_brand
from .models import Campaign, Company, Form, FormResponse, Tunnel, User
from .schemas import BrandAnalyzeRequest, CompanyUpdate, LoginIn, SiteBrandRequest
from .security import admin_user, client_ip, create_token, current_user, rate_limit, verify_password, write_user


router = APIRouter()


# Limitation de débit, par adresse IP. Seules les tentatives ratées comptent
# pour la connexion : un usage normal n'est jamais bloqué.
LOGIN_FAILURES, LOGIN_WINDOW = 10, 15 * 60

# Le relais de visuels refait l'appel sortant a chaque requete, sans cache
# serveur : marteler une URL signee immobilise un worker jusqu'a dix secondes.
# Large, parce que le navigateur garde l'image un jour et qu'une seule adresse
# peut porter beaucoup de visiteurs : environ dix visuels par nouveau
# visiteur, donc trente visiteurs par dix minutes pour une meme sortie.
BRAND_IMAGES, BRAND_IMAGE_WINDOW = 300, 10 * 60


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


@router.post("/api/auth/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    rate_limit("login", ip, limit=LOGIN_FAILURES, window_seconds=LOGIN_WINDOW, record=False)
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not verify_password(data.password, user.password_hash):
        rate_limit("login", ip, limit=LOGIN_FAILURES, window_seconds=LOGIN_WINDOW)
        raise HTTPException(401, "Email ou mot de passe incorrect")
    return {"access_token": create_token(user), "token_type": "bearer"}


@router.get("/api/me")
def me(user: User = Depends(current_user)):
    c = user.company
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role, "company": {"id": c.id, "name": c.name, "legal_name": c.legal_name, "sector": c.sector, "siret": c.siret, "address": c.address, "primary_color": c.primary_color, "accent_color": c.accent_color, "tone": c.tone, "dpo_email": c.dpo_email, "logo": c.logo, "brand": c.brand or {}}}


@router.get("/api/luna/status")
def luna_status(_: User = Depends(current_user)):
    configured = bool(settings.openai_api_key)
    return {
        "configured": configured,
        "provider": "openai" if configured else "local",
        "model": settings.openai_model if configured else None,
    }


@router.patch("/api/company")
def update_company(data: CompanyUpdate, db: Session = Depends(get_db), user: User = Depends(admin_user)):
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(user.company, key, value)
    db.commit()
    return me(user)


@router.post("/api/company/brand/analyze")
def analyze_company_brand(data: BrandAnalyzeRequest, user: User = Depends(write_user)):
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


@router.post("/api/brand/from-site")
def brand_from_site(data: SiteBrandRequest, user: User = Depends(write_user)):
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


@router.get("/api/brand/image")
def brand_image(request: Request, u: str = Query(max_length=2000), s: str = Query(max_length=64)):
    """Sert un visuel du site d'un client depuis notre origine.

    Publique et sans jeton, puisque les visiteurs de la page doivent la charger,
    mais signee : sans la signature, l'API serait un relais ouvert vers
    n'importe quelle adresse.
    """
    # Avant la signature : c'est la seule place qui plafonne aussi les requetes
    # non signees, et donc le travail total de cette route.
    rate_limit("brand-image", client_ip(request), limit=BRAND_IMAGES, window_seconds=BRAND_IMAGE_WINDOW)
    if not hmac.compare_digest(s, sign_image(u, settings.secret_key)):
        raise HTTPException(404, "Visuel introuvable")
    try:
        contenu, type_mime = fetch_image(u)
    except SiteError as exc:
        raise HTTPException(404, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Ce visuel n'a pas répondu.") from exc
    # Ouverte directement, l'adresse ne doit jamais devenir un document actif :
    # le navigateur ne devine pas le type, et rien ne s'execute.
    return Response(contenu, media_type=type_mime,
                    headers={"Cache-Control": "public, max-age=86400",
                             "X-Content-Type-Options": "nosniff",
                             "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.get("/api/stats")
def stats(db: Session = Depends(get_db), user: User = Depends(current_user)):
    forms = db.scalars(
        select(Form).join(Campaign, Form.campaign_id == Campaign.id)
        .where(Campaign.company_id == user.company_id, Campaign.archived.is_(False), Form.archived.is_(False))
    ).all()
    ids = [f.id for f in forms]
    campaigns = db.scalar(select(func.count(Campaign.id)).where(
        Campaign.company_id == user.company_id, Campaign.archived.is_(False),
        ~Campaign.tunnels.any(Tunnel.kind == "sales"))) or 0
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


@router.get("/api/team")
def team(db: Session = Depends(get_db), user: User = Depends(current_user)):
    members = db.scalars(select(User).where(User.company_id == user.company_id).order_by(User.created_at)).all()
    return [{"id": m.id, "full_name": m.full_name, "email": m.email, "role": m.role} for m in members]
