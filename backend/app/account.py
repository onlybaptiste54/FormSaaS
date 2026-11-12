"""Connexion, compte, marque de l'entreprise, statistiques et equipe."""

import hmac
import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .brand_site import SiteError, fetch_image, read_site, sign_image
from .luna import LunaAPIError, analyze_brand, analyze_site_brand
from .mailer import send_mail
from .models import Campaign, Company, Form, FormResponse, Invitation, PasswordReset, Tunnel, User, now
from .schemas import (AcceptInvitationIn, BrandAnalyzeRequest, CompanyUpdate, ForgotPasswordIn, InvitationTokenIn,
                      InviteIn, LoginIn, ResetPasswordIn, SiteBrandRequest)
from .security import (admin_user, client_ip, create_token, current_user, hash_link_token, hash_password,
                       new_link_token, rate_limit, verify_password, write_user)


router = APIRouter()
logger = logging.getLogger(__name__)


# Limitation de débit, par adresse IP. Seules les tentatives ratées comptent
# pour la connexion : un usage normal n'est jamais bloqué.
LOGIN_FAILURES, LOGIN_WINDOW = 10, 15 * 60

# Mot de passe oublié : la demande est toujours comptée, même pour une adresse
# inconnue, sinon la limite révélerait quelles adresses ont un compte.
FORGOT_PER_IP, FORGOT_IP_WINDOW = 5, 15 * 60
FORGOT_PER_EMAIL, FORGOT_EMAIL_WINDOW = 3, 60 * 60
INVITES_PER_COMPANY, INVITE_WINDOW = 20, 60 * 60

RESET_VALIDITY = timedelta(hours=1)
INVITATION_VALIDITY = timedelta(days=7)

INVALID_RESET = "Ce lien n'est plus valable. Demandez-en un nouveau."
INVALID_INVITATION = ("Cette invitation n'est plus valable. "
                      "Demandez à votre administrateur de vous en renvoyer une.")
ROLE_LABELS = {"admin": "administrateur", "creator": "créateur", "viewer": "lecteur"}

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


# --- Mot de passe oublié -----------------------------------------------------


def send_reset_mail(email: str, token: str) -> None:
    """Part en tâche de fond : un serveur SMTP lent ne retient pas la requête."""
    try:
        send_mail(
            email,
            "Réinitialisation de votre mot de passe Sillage",
            "Bonjour,\n\n"
            "Pour choisir un nouveau mot de passe, ouvrez ce lien :\n"
            f"{settings.site_url}/reset-password#{token}\n\n"
            "Ce lien est valable une heure et ne sert qu'une fois.\n"
            "Si vous n'avez rien demandé, ignorez ce message : votre mot de passe reste inchangé.\n",
        )
    except Exception:
        # Sans le lien : il donnerait accès au compte à qui lit les logs.
        logger.exception("Envoi du lien de réinitialisation impossible")


@router.post("/api/auth/forgot-password")
def forgot_password(data: ForgotPasswordIn, request: Request, background: BackgroundTasks,
                    db: Session = Depends(get_db)):
    email = data.email.lower()
    rate_limit("forgot-ip", client_ip(request), limit=FORGOT_PER_IP, window_seconds=FORGOT_IP_WINDOW)
    rate_limit("forgot-email", email, limit=FORGOT_PER_EMAIL, window_seconds=FORGOT_EMAIL_WINDOW)
    user = db.scalar(select(User).where(User.email == email))
    if user:
        db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)))
        token = new_link_token()
        db.add(PasswordReset(user_id=user.id, token_hash=hash_link_token(token),
                             expires_at=now() + RESET_VALIDITY))
        db.commit()
        background.add_task(send_reset_mail, email, token)
    # Même réponse que le compte existe ou non.
    return {"detail": "Si un compte existe pour cette adresse, un lien vient d'y être envoyé."}


@router.post("/api/auth/reset-password")
def reset_password(data: ResetPasswordIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    rate_limit("reset", ip, limit=LOGIN_FAILURES, window_seconds=LOGIN_WINDOW, record=False)
    # L'échéance se compare en SQL : SQLite rend des dates sans fuseau.
    reset = db.scalar(select(PasswordReset).where(
        PasswordReset.token_hash == hash_link_token(data.token),
        PasswordReset.used_at.is_(None), PasswordReset.expires_at > now()))
    # Le marquage « utilisé » est atomique : deux requêtes simultanées ne passent pas toutes les deux.
    claimed = reset and db.execute(update(PasswordReset).where(
        PasswordReset.id == reset.id, PasswordReset.used_at.is_(None)).values(used_at=now())).rowcount == 1
    if not claimed:
        db.rollback()
        rate_limit("reset", ip, limit=LOGIN_FAILURES, window_seconds=LOGIN_WINDOW)
        raise HTTPException(400, INVALID_RESET)
    user = db.get(User, reset.user_id)
    user.password_hash = hash_password(data.password)
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.id != reset.id))
    db.commit()
    return {"detail": "Mot de passe enregistré."}


# --- Invitations -------------------------------------------------------------


def pending_invitation(db: Session, token: str, ip: str) -> Invitation:
    """L'invitation que ce jeton ouvre, ou 400 (et un échec compté pour cette adresse)."""
    rate_limit("invitation", ip, limit=LOGIN_FAILURES, window_seconds=LOGIN_WINDOW, record=False)
    invitation = db.scalar(select(Invitation).where(
        Invitation.token_hash == hash_link_token(token),
        Invitation.accepted_at.is_(None), Invitation.expires_at > now()))
    if not invitation:
        rate_limit("invitation", ip, limit=LOGIN_FAILURES, window_seconds=LOGIN_WINDOW)
        raise HTTPException(400, INVALID_INVITATION)
    return invitation


def invitation_out(invitation: Invitation) -> dict:
    return {"id": invitation.id, "email": invitation.email, "role": invitation.role,
            "created_at": invitation.created_at.isoformat(), "expires_at": invitation.expires_at.isoformat()}


@router.post("/api/auth/invitation")
def check_invitation(data: InvitationTokenIn, request: Request, db: Session = Depends(get_db)):
    invitation = pending_invitation(db, data.token, client_ip(request))
    company = db.get(Company, invitation.company_id)
    return {"company": company.name, "email": invitation.email, "role": invitation.role}


@router.post("/api/auth/accept-invitation")
def accept_invitation(data: AcceptInvitationIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    invitation = pending_invitation(db, data.token, ip)
    if db.scalar(select(User.id).where(User.email == invitation.email)):
        raise HTTPException(409, "Un compte existe déjà avec cette adresse. Connectez-vous.")
    # Même précaution que pour la réinitialisation : une invitation ne sert qu'une fois.
    claimed = db.execute(update(Invitation).where(
        Invitation.id == invitation.id, Invitation.accepted_at.is_(None)).values(accepted_at=now()))
    if claimed.rowcount != 1:
        db.rollback()
        rate_limit("invitation", ip, limit=LOGIN_FAILURES, window_seconds=LOGIN_WINDOW)
        raise HTTPException(400, INVALID_INVITATION)
    user = User(company_id=invitation.company_id, email=invitation.email, full_name=data.full_name.strip(),
                password_hash=hash_password(data.password), role=invitation.role)
    db.add(user)
    db.commit()
    return {"access_token": create_token(user), "token_type": "bearer"}


@router.get("/api/team/invitations")
def list_invitations(db: Session = Depends(get_db), user: User = Depends(admin_user)):
    pending = db.scalars(select(Invitation).where(
        Invitation.company_id == user.company_id, Invitation.accepted_at.is_(None),
        Invitation.expires_at > now()).order_by(Invitation.created_at)).all()
    return [invitation_out(i) for i in pending]


@router.post("/api/team/invitations")
def invite_member(data: InviteIn, db: Session = Depends(get_db), user: User = Depends(admin_user)):
    rate_limit("invite", user.company_id, limit=INVITES_PER_COMPANY, window_seconds=INVITE_WINDOW)
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Un compte existe déjà avec cette adresse.")
    token = new_link_token()
    invitation = Invitation(company_id=user.company_id, email=email, role=data.role,
                            token_hash=hash_link_token(token), invited_by=user.id,
                            expires_at=now() + INVITATION_VALIDITY)
    db.add(invitation)
    db.commit()
    company = db.get(Company, user.company_id)
    try:
        # Synchrone : l'administrateur doit savoir si le message n'est pas parti.
        send_mail(
            email,
            f"Invitation à rejoindre {company.name} sur Sillage",
            "Bonjour,\n\n"
            f"{user.full_name} vous invite à rejoindre {company.name} sur Sillage, "
            f"avec le rôle {ROLE_LABELS[data.role]}.\n\n"
            "Pour créer votre compte, ouvrez ce lien :\n"
            f"{settings.site_url}/invitation#{token}\n\n"
            "Ce lien est valable 7 jours.\n",
        )
    except Exception as exc:
        logger.exception("Envoi de l'invitation impossible")
        db.delete(invitation)
        db.commit()
        raise HTTPException(502, "L'e-mail n'a pas pu partir. Vérifiez la configuration SMTP de l'API.") from exc
    # Renvoyer une invitation remplace la précédente, une fois la nouvelle partie.
    db.execute(delete(Invitation).where(
        Invitation.company_id == user.company_id, Invitation.email == email,
        Invitation.accepted_at.is_(None), Invitation.id != invitation.id))
    db.commit()
    return invitation_out(invitation)


@router.delete("/api/team/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: str, db: Session = Depends(get_db), user: User = Depends(admin_user)):
    invitation = db.scalar(select(Invitation).where(
        Invitation.id == invitation_id, Invitation.company_id == user.company_id))
    if not invitation:
        raise HTTPException(404, "Invitation introuvable")
    db.delete(invitation)
    db.commit()
