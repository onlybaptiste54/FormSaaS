import base64
import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import DEV_SECRET_KEY, MIN_SECRET_LENGTH, is_production, settings
from .database import get_db
from .models import User


bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"{base64.b64encode(salt).decode()}:{base64.b64encode(derived).decode()}"


def verify_password(password: str, stored: str) -> bool:
    salt_b64, expected_b64 = stored.split(":", 1)
    candidate = hash_password(password, base64.b64decode(salt_b64)).split(":", 1)[1]
    return hmac.compare_digest(candidate, expected_b64)


def create_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "company": user.company_id,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(401, "Authentification requise")
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Session invalide") from exc
    user = db.get(User, payload.get("sub"))
    if not user:
        raise HTTPException(401, "Utilisateur introuvable")
    return user


# --- Rôles -------------------------------------------------------------------

# Qui peut écrire. Un lecteur consulte les campagnes, il ne les modifie pas.
WRITE_ROLES = ("admin", "creator")


def write_user(user: User = Depends(current_user)) -> User:
    """Toute route qui modifie des données passe par ici."""
    if user.role not in WRITE_ROLES:
        raise HTTPException(403, "Votre rôle ne permet pas de modifier les campagnes.")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    """Réglages de l'entreprise et suppression définitive d'une réponse."""
    if user.role != "admin":
        raise HTTPException(403, "Seul un administrateur peut effectuer cette action.")
    return user


# --- Limitation de débit -----------------------------------------------------

# Fenêtre glissante en mémoire : suffisante contre un script, et sans dépendance
# ni service externe. Chaque worker compte pour lui-même, donc la limite réelle
# est multipliée par le nombre de workers ; au-delà, il faudra un compteur
# partagé (Redis ou la base).
_HITS: dict[tuple[str, str], list[float]] = {}
# Au-delà, on balaie les clés expirées pour que la mémoire ne grossisse pas avec
# le nombre d'adresses vues.
_SWEEP_ABOVE = 2048


def client_ip(request: Request) -> str:
    """Adresse vue par l'API.

    `X-Forwarded-For` n'est pas lu : n'importe qui peut l'écrire, et la limite
    deviendrait contournable. Derrière un proxy, lancer uvicorn avec
    --proxy-headers et --forwarded-allow-ips pour que cette adresse soit juste.
    """
    return request.client.host if request.client else "inconnu"


def rate_limit(bucket: str, key: str, *, limit: int, window_seconds: int, record: bool = True) -> None:
    """Refuse la requête au-delà de `limit` passages dans la fenêtre.

    `record=False` ne fait que vérifier : la connexion s'en sert pour ne
    compter que les tentatives ratées, et ne jamais bloquer un usage normal.
    """
    now = time.monotonic()
    if len(_HITS) > _SWEEP_ABOVE:
        for stale, hits in list(_HITS.items()):
            if not hits or now - hits[-1] >= window_seconds:
                del _HITS[stale]
    recent = [moment for moment in _HITS.get((bucket, key), []) if now - moment < window_seconds]
    if len(recent) >= limit:
        _HITS[(bucket, key)] = recent
        retry_after = max(1, int(window_seconds - (now - recent[0])) + 1)
        raise HTTPException(429, "Trop de tentatives. Patientez un instant avant de réessayer.",
                            headers={"Retry-After": str(retry_after)})
    if record:
        recent.append(now)
    _HITS[(bucket, key)] = recent


def reset_rate_limits() -> None:
    """Remet les compteurs à zéro (tests, et redémarrage à chaud)."""
    _HITS.clear()


# --- Démarrage ---------------------------------------------------------------


def ensure_production_secrets() -> None:
    """Refuse de démarrer en production avec la clé de développement.

    Cette clé signe les jetons d'authentification et le cookie de parcours
    public : connue, elle les rend forgeables.
    """
    if not is_production():
        return
    if settings.secret_key == DEV_SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY vaut encore la clé de développement alors que ENVIRONMENT=production. "
            "Générez-en une avec : python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    if len(settings.secret_key) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"SECRET_KEY fait {len(settings.secret_key)} caractères : il en faut au moins "
            f"{MIN_SECRET_LENGTH} en production. Générez-en une avec : "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )
