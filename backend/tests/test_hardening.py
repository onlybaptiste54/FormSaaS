"""Durcissement avant mise en ligne : cle de signature, debit, roles."""

import os
import tempfile

import pytest

# DATABASE_URL doit etre pose avant le premier import de `app` : le moteur nait
# au chargement de app.database et le premier chargement gagne. Plusieurs tests
# d'ici importent `app` sans passer par la fixture ; sans cette ligne, ils
# ecriraient dans backend/sillage.db.
_HANDLE, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_HANDLE)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    from app.database import engine

    # Windows garde le fichier ouvert tant que le moteur vit.
    engine.dispose()
    os.unlink(_DB_PATH)


def token_for(role: str) -> str:
    """Un membre de l'entreprise de demonstration, avec le role demande."""
    from app.database import SessionLocal
    from app.models import Company, User
    from app.security import create_token, hash_password

    with SessionLocal() as db:
        company = db.query(Company).first()
        email = f"{role}@sillage.fr"
        user = db.query(User).filter(User.email == email).one_or_none()
        if not user:
            user = User(company_id=company.id, email=email, full_name=role.capitalize(),
                        password_hash=hash_password("motdepasse1234"), role=role)
            db.add(user)
            db.commit()
            db.refresh(user)
        return create_token(user)


def auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(role)}"}


# --- La cle de signature -----------------------------------------------------


def test_production_refuses_the_development_key(monkeypatch):
    from app.config import DEV_SECRET_KEY, settings
    from app.security import ensure_production_secrets

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", DEV_SECRET_KEY)
    with pytest.raises(RuntimeError) as refusal:
        ensure_production_secrets()
    assert "SECRET_KEY" in str(refusal.value)
    assert "token_hex" in str(refusal.value)


def test_production_refuses_a_short_key(monkeypatch):
    from app.config import settings
    from app.security import ensure_production_secrets

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", "trop-court")
    with pytest.raises(RuntimeError, match="au moins"):
        ensure_production_secrets()


def test_production_accepts_a_real_key(monkeypatch):
    import secrets

    from app.config import settings
    from app.security import ensure_production_secrets

    monkeypatch.setattr(settings, "environment", "PRODUCTION ")
    monkeypatch.setattr(settings, "secret_key", secrets.token_hex(32))
    ensure_production_secrets()


def test_development_keeps_the_quick_start_working(monkeypatch):
    from app.config import DEV_SECRET_KEY, settings
    from app.security import ensure_production_secrets

    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "secret_key", DEV_SECRET_KEY)
    ensure_production_secrets()


# --- La limitation de debit --------------------------------------------------


def test_only_failed_logins_count(client):
    from app.main import LOGIN_FAILURES

    good = {"email": "demo@sillage.fr", "password": "demo1234"}
    for _ in range(LOGIN_FAILURES + 5):
        assert client.post("/api/auth/login", json=good).status_code == 200

    for attempt in range(LOGIN_FAILURES):
        refused = client.post("/api/auth/login", json={**good, "password": "faux"})
        assert refused.status_code == 401, f"tentative {attempt}"

    blocked = client.post("/api/auth/login", json={**good, "password": "faux"})
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    # Le mot de passe juste ne rouvre pas la porte avant la fin de la fenetre.
    assert client.post("/api/auth/login", json=good).status_code == 429


def test_public_submissions_are_capped(client):
    from app.main import SUBMISSIONS

    payload = {"answers": {"email": "visiteur@exemple.fr"}, "consent": True}
    for attempt in range(SUBMISSIONS):
        # Le formulaire n'existe pas : seul le compteur nous interesse ici.
        assert client.post("/api/public/slug-inconnu/submit", json=payload).status_code == 404, f"envoi {attempt}"
    assert client.post("/api/public/slug-inconnu/submit", json=payload).status_code == 429


def test_the_image_relay_is_capped(client, monkeypatch):
    """Le relais refait l'appel sortant a chaque requete : il doit etre plafonne.

    La limite passe avant la verification de signature, donc une rafale non
    signee compte aussi. Le plafond est abaisse ici pour ne pas tirer trois
    cents requetes dans un test.
    """
    monkeypatch.setattr("app.main.BRAND_IMAGES", 3)
    for attempt in range(3):
        refused = client.get("/api/brand/image", params={"u": "https://exemple.fr/logo.png", "s": "fausse"})
        assert refused.status_code == 404, f"appel {attempt}"
    blocked = client.get("/api/brand/image", params={"u": "https://exemple.fr/logo.png", "s": "fausse"})
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_the_relay_never_fetches_without_a_valid_signature(client, monkeypatch):
    """Signature fausse : 404 avant tout appel sortant.

    Le nom est remplace dans app.main, ou il est importe : le patcher dans
    app.brand_site ne changerait rien et ce test passerait a vide.
    """
    def jamais(*_args, **_kwargs):
        raise AssertionError("fetch_image ne doit pas etre appele sans signature valide")

    monkeypatch.setattr("app.main.fetch_image", jamais)
    assert client.get("/api/brand/image", params={"u": "https://exemple.fr/x.png", "s": "fausse"}).status_code == 404


def test_tinycss2_is_declared(client):
    """brand_site.py l'importe : il ne doit pas dependre d'un extra de bleach."""
    from pathlib import Path

    declared = Path(__file__).resolve().parents[1] / "requirements.txt"
    lignes = [ligne.split("==")[0] for ligne in declared.read_text(encoding="utf-8").splitlines()
              if ligne.strip() and not ligne.startswith("#")]
    assert "tinycss2" in lignes


def test_the_window_counts_per_usage(client):
    """Saturer la connexion ne ferme pas la collecte, et inversement."""
    from app.main import LOGIN_FAILURES

    for _ in range(LOGIN_FAILURES):
        client.post("/api/auth/login", json={"email": "demo@sillage.fr", "password": "faux"})
    assert client.post("/api/auth/login", json={"email": "demo@sillage.fr", "password": "faux"}).status_code == 429
    assert client.post("/api/public/slug-inconnu/submit",
                       json={"answers": {"email": "a@b.fr"}, "consent": True}).status_code == 404


# --- Les roles ---------------------------------------------------------------


NEW_CAMPAIGN = {"name": "Campagne de controle", "client": "Interne", "objective": "Verifier les roles"}


def test_a_viewer_reads_but_never_writes(client):
    assert client.get("/api/campaigns", headers=auth("viewer")).status_code == 200
    refused = client.post("/api/campaigns", json=NEW_CAMPAIGN, headers=auth("viewer"))
    assert refused.status_code == 403
    assert "rôle" in refused.json()["detail"]


def test_a_creator_writes_campaigns(client):
    created = client.post("/api/campaigns", json=NEW_CAMPAIGN, headers=auth("creator"))
    assert created.status_code == 201, created.text
    # Les modules partagent la base : on archive pour ne pas fausser les
    # comptages des autres tests.
    archived = client.patch(f"/api/campaigns/{created.json()['id']}", json={"archived": True},
                            headers=auth("creator"))
    assert archived.status_code == 200


def test_company_settings_stay_with_the_admin(client):
    assert client.patch("/api/company", json={"tone": "Direct"}, headers=auth("creator")).status_code == 403
    assert client.patch("/api/company", json={"tone": "Direct"}, headers=auth("viewer")).status_code == 403
    assert client.patch("/api/company", json={"tone": "Direct"}, headers=auth("admin")).status_code == 200


def test_deleting_a_response_stays_with_the_admin(client):
    """403 contre 404 : seul l'administrateur franchit le controle de role.

    On vise un identifiant inexistant pour ne supprimer aucune reponse de
    demonstration : ce qui est verifie ici, c'est le garde, pas la suppression.
    """
    inconnu = "00000000-0000-0000-0000-000000000000"
    assert client.delete(f"/api/responses/{inconnu}", headers=auth("viewer")).status_code == 403
    assert client.delete(f"/api/responses/{inconnu}", headers=auth("creator")).status_code == 403
    assert client.delete(f"/api/responses/{inconnu}", headers=auth("admin")).status_code == 404


def test_every_write_route_is_guarded():
    """Aucune route d'ecriture ne doit retomber sur current_user."""
    from app.main import app
    from app.security import admin_user, current_user, write_user

    unguarded = []
    for route in app.routes:
        methods = getattr(route, "methods", set()) - {"GET", "HEAD", "OPTIONS"}
        if not methods or not getattr(route, "dependant", None):
            continue
        guards = {dependency.call for dependency in route.dependant.dependencies}
        if current_user in guards and not guards & {write_user, admin_user}:
            unguarded.append(f"{sorted(methods)[0]} {route.path}")
    assert not unguarded, f"routes d'ecriture sans controle de role : {unguarded}"


# --- Le premier compte ------------------------------------------------------


@pytest.fixture
def blank_db(tmp_path):
    """Base vide et isolee : le seed de demonstration s'y voit ou ne s'y voit pas."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'vierge.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def test_production_creates_no_demo_account(monkeypatch, blank_db, caplog):
    import logging

    from sqlalchemy import select

    from app.config import settings
    from app.models import Campaign, User
    from app.seed import seed

    monkeypatch.setattr(settings, "environment", "production")
    with caplog.at_level(logging.WARNING):
        seed(blank_db)
    assert blank_db.scalars(select(User)).all() == []
    assert blank_db.scalars(select(Campaign)).all() == []
    assert "python -m app.admin" in caplog.text


def test_development_still_gets_the_demo_account(monkeypatch, blank_db):
    from sqlalchemy import select

    from app.config import settings
    from app.models import User
    from app.seed import seed

    monkeypatch.setattr(settings, "environment", "development")
    seed(blank_db)
    accounts = blank_db.scalars(select(User)).all()
    assert [user.email for user in accounts] == ["demo@sillage.fr"]


def test_the_first_admin_opens_the_door_once(blank_db):
    from app.admin import create_first_admin
    from app.schemas import FirstAdminIn
    from app.security import verify_password

    account = FirstAdminIn(email="Patron@Exemple.FR", password="motdepasse-solide",
                           full_name="Camille Patron", company_name="Atelier Exemple")
    created = create_first_admin(blank_db, account)
    assert created.role == "admin"
    # La connexion compare une adresse en minuscules.
    assert created.email == "patron@exemple.fr"
    assert verify_password("motdepasse-solide", created.password_hash)
    assert created.company.name == "Atelier Exemple"

    with pytest.raises(ValueError, match="existe déjà"):
        create_first_admin(blank_db, account)


def test_a_short_password_is_refused():
    from pydantic import ValidationError

    from app.schemas import FirstAdminIn

    with pytest.raises(ValidationError):
        FirstAdminIn(email="patron@exemple.fr", password="court", full_name="Camille",
                     company_name="Atelier Exemple")


def test_the_command_refuses_a_base_already_in_service(client, monkeypatch):
    from app.admin import main

    monkeypatch.setenv("ADMIN_PASSWORD", "motdepasse-solide")
    assert main(["--email", "autre@exemple.fr", "--company", "Atelier Exemple"]) == 1


def test_the_command_refuses_a_bad_account(monkeypatch):
    from app.admin import main

    monkeypatch.setenv("ADMIN_PASSWORD", "court")
    assert main(["--email", "patron@exemple.fr", "--company", "Atelier Exemple"]) == 2
    monkeypatch.setenv("ADMIN_PASSWORD", "motdepasse-solide")
    assert main(["--email", "pas-une-adresse", "--company", "Atelier Exemple"]) == 2


def test_the_password_never_needs_the_command_line(monkeypatch):
    from app.admin import read_password

    monkeypatch.setenv("ADMIN_PASSWORD", "depuis-l-environnement")
    assert read_password(None) == "depuis-l-environnement"
    assert read_password("explicite") == "explicite"
    monkeypatch.delenv("ADMIN_PASSWORD")
    monkeypatch.setattr("getpass.getpass", lambda _: "saisi-deux-fois")
    assert read_password(None) == "saisi-deux-fois"

    saisies = iter(["premier", "different"])
    monkeypatch.setattr("getpass.getpass", lambda _: next(saisies))
    with pytest.raises(ValueError, match="diffèrent"):
        read_password(None)
