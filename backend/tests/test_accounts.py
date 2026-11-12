"""Mot de passe oublié, invitations de collègues et envoi d'e-mails."""

import logging
import os
import re
import tempfile
from datetime import timedelta
from types import SimpleNamespace

import pytest

# Comme test_hardening : DATABASE_URL se pose avant le premier import de `app`,
# sinon ce fichier (le premier collecté) ecrirait dans backend/sillage.db.
_HANDLE, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_HANDLE)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"

PASSWORD = "motdepasse1234"


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


@pytest.fixture
def mails(monkeypatch):
    """Les messages que l'API aurait envoyés."""
    sent = []
    monkeypatch.setattr("app.account.send_mail", lambda to, subject, body: sent.append(
        SimpleNamespace(to=to, subject=subject, body=body)))
    return sent


def make_user(email: str, role: str = "admin", company_name: str | None = None, company_id: str | None = None):
    """Un compte à part, dans une nouvelle entreprise ou dans celle donnée."""
    from app.database import SessionLocal
    from app.models import Company, User
    from app.security import create_token, hash_password

    with SessionLocal() as db:
        if company_id is None:
            company = Company(name=company_name or "Entreprise test")
            db.add(company)
            db.flush()
            company_id = company.id
        user = User(company_id=company_id, email=email, full_name="Test", role=role,
                    password_hash=hash_password(PASSWORD))
        db.add(user)
        db.commit()
        return SimpleNamespace(id=user.id, company_id=company_id,
                               headers={"Authorization": f"Bearer {create_token(user)}"})


def link_token(mail) -> str:
    """Le jeton porté par le fragment du lien, tel que l'ouvre le navigateur."""
    return re.search(r"#([\w-]+)", mail.body).group(1)


def login(client, email: str, password: str):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# --- Mot de passe oublié -----------------------------------------------------


def test_forgot_password_answers_the_same_for_known_and_unknown_emails(client, mails):
    make_user("oubli@exemple.fr")

    known = client.post("/api/auth/forgot-password", json={"email": "Oubli@exemple.fr"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "personne@exemple.fr"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert [m.to for m in mails] == ["oubli@exemple.fr"]
    assert "/reset-password#" in mails[0].body


def test_reset_link_works_once_then_login_uses_the_new_password(client, mails):
    make_user("unefois@exemple.fr")
    client.post("/api/auth/forgot-password", json={"email": "unefois@exemple.fr"})
    token = link_token(mails[0])

    done = client.post("/api/auth/reset-password", json={"token": token, "password": "nouveau-mot-de-passe"})
    assert done.status_code == 200
    assert login(client, "unefois@exemple.fr", "nouveau-mot-de-passe").status_code == 200
    assert login(client, "unefois@exemple.fr", PASSWORD).status_code == 401

    again = client.post("/api/auth/reset-password", json={"token": token, "password": "encore-un-autre-mdp"})
    assert again.status_code == 400
    assert "n'est plus valable" in again.json()["detail"]


def test_a_new_request_replaces_the_previous_link(client, mails):
    make_user("remplace@exemple.fr")
    client.post("/api/auth/forgot-password", json={"email": "remplace@exemple.fr"})
    client.post("/api/auth/forgot-password", json={"email": "remplace@exemple.fr"})

    old, new = link_token(mails[0]), link_token(mails[1])
    assert client.post("/api/auth/reset-password", json={"token": old, "password": PASSWORD}).status_code == 400
    assert client.post("/api/auth/reset-password", json={"token": new, "password": PASSWORD}).status_code == 200


def test_expired_reset_token_is_refused_with_400(client, mails):
    from app.database import SessionLocal
    from app.models import PasswordReset, now

    user = make_user("expire@exemple.fr")
    client.post("/api/auth/forgot-password", json={"email": "expire@exemple.fr"})
    with SessionLocal() as db:
        # SQLite rend des dates sans fuseau : l'échéance doit se comparer en SQL.
        for reset in db.query(PasswordReset).filter(PasswordReset.user_id == user.id):
            reset.expires_at = now() - timedelta(minutes=1)
        db.commit()

    refused = client.post("/api/auth/reset-password", json={"token": link_token(mails[0]), "password": PASSWORD})
    assert refused.status_code == 400


def test_reset_token_still_valid_before_its_deadline(client, mails):
    from app.database import SessionLocal
    from app.models import PasswordReset, now

    user = make_user("encore@exemple.fr")
    client.post("/api/auth/forgot-password", json={"email": "encore@exemple.fr"})
    with SessionLocal() as db:
        for reset in db.query(PasswordReset).filter(PasswordReset.user_id == user.id):
            reset.expires_at = now() + timedelta(minutes=1)
        db.commit()

    ok = client.post("/api/auth/reset-password", json={"token": link_token(mails[0]), "password": PASSWORD})
    assert ok.status_code == 200


def test_reset_refuses_an_unknown_token_and_a_short_password(client, mails):
    unknown = client.post("/api/auth/reset-password", json={"token": "inconnu", "password": PASSWORD})
    assert unknown.status_code == 400

    make_user("court@exemple.fr")
    client.post("/api/auth/forgot-password", json={"email": "court@exemple.fr"})
    short = client.post("/api/auth/reset-password", json={"token": link_token(mails[0]), "password": "court"})
    assert short.status_code == 422


def test_forgot_password_is_rate_limited_and_the_limit_does_not_reveal_accounts(client, mails):
    statuses = [client.post("/api/auth/forgot-password", json={"email": "inconnu@exemple.fr"}).status_code
                for _ in range(4)]
    assert statuses == [200, 200, 200, 429]


def test_forgot_password_is_rate_limited_per_ip(client, mails):
    statuses = [client.post("/api/auth/forgot-password", json={"email": f"a{n}@exemple.fr"}).status_code
                for n in range(6)]
    assert statuses == [200] * 5 + [429]


def test_a_failed_background_send_is_logged_without_the_link(client, monkeypatch, caplog):
    make_user("panne@exemple.fr")

    def broken(to, subject, body):
        raise OSError("SMTP injoignable")

    monkeypatch.setattr("app.account.send_mail", broken)
    with caplog.at_level(logging.ERROR, logger="app.account"):
        response = client.post("/api/auth/forgot-password", json={"email": "panne@exemple.fr"})

    assert response.status_code == 200
    assert "Envoi du lien de réinitialisation impossible" in caplog.text
    assert "/reset-password#" not in caplog.text


# --- Invitations -------------------------------------------------------------


def invite(client, admin, email: str, role: str = "creator"):
    return client.post("/api/team/invitations", json={"email": email, "role": role}, headers=admin.headers)


def test_only_an_admin_can_manage_invitations(client, mails):
    company = make_user("chef-droits@exemple.fr")
    for role in ("creator", "viewer"):
        member = make_user(f"{role}-droits@exemple.fr", role=role, company_id=company.company_id)
        assert client.get("/api/team/invitations", headers=member.headers).status_code == 403
        assert invite(client, member, "x@exemple.fr").status_code == 403
        assert client.delete("/api/team/invitations/abc", headers=member.headers).status_code == 403
    assert mails == []


def test_invitation_flow_creates_the_user_in_the_right_company(client, mails):
    admin = make_user("chef-flux@exemple.fr", company_name="Atelier Flux")

    sent = invite(client, admin, "Nouvelle@Exemple.fr", role="viewer")
    assert sent.status_code == 200
    assert sent.json()["email"] == "nouvelle@exemple.fr"
    assert sent.json()["role"] == "viewer"
    assert len(mails) == 1
    assert mails[0].to == "nouvelle@exemple.fr"
    assert mails[0].subject == "Invitation à rejoindre Atelier Flux sur Sillage"
    assert "lecteur" in mails[0].body and "7 jours" in mails[0].body and "/invitation#" in mails[0].body
    token = link_token(mails[0])

    check = client.post("/api/auth/invitation", json={"token": token})
    assert check.status_code == 200
    assert check.json() == {"company": "Atelier Flux", "email": "nouvelle@exemple.fr", "role": "viewer"}

    accepted = client.post("/api/auth/accept-invitation",
                           json={"token": token, "full_name": "Nina Durand", "password": PASSWORD})
    assert accepted.status_code == 200
    me = client.get("/api/me", headers={"Authorization": f"Bearer {accepted.json()['access_token']}"}).json()
    assert me["email"] == "nouvelle@exemple.fr"
    assert me["role"] == "viewer"
    assert me["full_name"] == "Nina Durand"
    assert me["company"]["id"] == admin.company_id
    assert login(client, "nouvelle@exemple.fr", PASSWORD).status_code == 200

    # Une invitation ne sert qu'une fois, et ne reste pas dans la liste.
    assert client.post("/api/auth/invitation", json={"token": token}).status_code == 400
    reuse = client.post("/api/auth/accept-invitation",
                        json={"token": token, "full_name": "Autre Nom", "password": PASSWORD})
    assert reuse.status_code == 400
    assert client.get("/api/team/invitations", headers=admin.headers).json() == []


def test_unknown_invitation_token_gets_400_never_401(client):
    check = client.post("/api/auth/invitation", json={"token": "inconnu"})
    assert check.status_code == 400
    assert "Demandez à votre administrateur" in check.json()["detail"]
    accept = client.post("/api/auth/accept-invitation",
                         json={"token": "inconnu", "full_name": "Nom Complet", "password": PASSWORD})
    assert accept.status_code == 400


def test_accept_validates_name_and_password(client, mails):
    admin = make_user("chef-valide@exemple.fr")
    invite(client, admin, "valide@exemple.fr")
    token = link_token(mails[0])

    short_password = client.post("/api/auth/accept-invitation",
                                 json={"token": token, "full_name": "Nom Complet", "password": "court"})
    short_name = client.post("/api/auth/accept-invitation",
                             json={"token": token, "full_name": "N", "password": PASSWORD})
    assert short_password.status_code == short_name.status_code == 422


def test_revoked_invitation_is_refused(client, mails):
    admin = make_user("chef-revoque@exemple.fr")
    created = invite(client, admin, "revoque@exemple.fr").json()

    assert client.delete(f"/api/team/invitations/{created['id']}", headers=admin.headers).status_code == 204
    assert client.post("/api/auth/invitation", json={"token": link_token(mails[0])}).status_code == 400
    assert client.get("/api/team/invitations", headers=admin.headers).json() == []


def test_another_company_cannot_revoke_an_invitation(client, mails):
    admin = make_user("chef-a@exemple.fr")
    other = make_user("chef-b@exemple.fr")
    created = invite(client, admin, "cible@exemple.fr").json()

    assert client.delete(f"/api/team/invitations/{created['id']}", headers=other.headers).status_code == 404
    assert client.post("/api/auth/invitation", json={"token": link_token(mails[0])}).status_code == 200
    assert client.get("/api/team/invitations", headers=other.headers).json() == []


def test_inviting_an_existing_user_is_refused(client, mails):
    admin = make_user("chef-existe@exemple.fr")
    make_user("deja@exemple.fr", company_id=admin.company_id)

    refused = invite(client, admin, "Deja@exemple.fr")
    assert refused.status_code == 409
    assert mails == []


def test_accepting_when_the_account_appeared_meanwhile_gives_409(client, mails):
    admin = make_user("chef-entre@exemple.fr")
    invite(client, admin, "entre@exemple.fr")
    make_user("entre@exemple.fr", company_id=admin.company_id)

    response = client.post("/api/auth/accept-invitation",
                           json={"token": link_token(mails[0]), "full_name": "Nom Complet", "password": PASSWORD})
    assert response.status_code == 409
    assert "Connectez-vous" in response.json()["detail"]


def test_inviting_twice_keeps_one_pending_invitation(client, mails):
    admin = make_user("chef-deux@exemple.fr")
    invite(client, admin, "deux@exemple.fr")
    invite(client, admin, "deux@exemple.fr", role="admin")

    pending = client.get("/api/team/invitations", headers=admin.headers).json()
    assert len(pending) == 1
    assert pending[0]["role"] == "admin"
    # Seul le dernier lien ouvre l'invitation.
    assert client.post("/api/auth/invitation", json={"token": link_token(mails[0])}).status_code == 400
    assert client.post("/api/auth/invitation", json={"token": link_token(mails[1])}).status_code == 200


def test_the_list_only_shows_pending_invitations_of_the_company(client, mails):
    from app.database import SessionLocal
    from app.models import Invitation, now

    admin = make_user("chef-liste@exemple.fr")
    other = make_user("chef-autre@exemple.fr")
    invite(client, admin, "attente@exemple.fr")
    invite(client, admin, "acceptee@exemple.fr")
    invite(client, admin, "perimee@exemple.fr")
    invite(client, other, "ailleurs@exemple.fr")
    with SessionLocal() as db:
        for invitation in db.query(Invitation).filter(Invitation.company_id == admin.company_id):
            if invitation.email == "acceptee@exemple.fr":
                invitation.accepted_at = now()
            if invitation.email == "perimee@exemple.fr":
                invitation.expires_at = now() - timedelta(minutes=1)
        db.commit()

    pending = client.get("/api/team/invitations", headers=admin.headers).json()
    assert [i["email"] for i in pending] == ["attente@exemple.fr"]
    assert set(pending[0]) == {"id", "email", "role", "created_at", "expires_at"}


def test_expired_invitation_is_refused(client, mails):
    from app.database import SessionLocal
    from app.models import Invitation, now

    admin = make_user("chef-perime@exemple.fr")
    invite(client, admin, "trop-tard@exemple.fr")
    with SessionLocal() as db:
        for invitation in db.query(Invitation).filter(Invitation.company_id == admin.company_id):
            invitation.expires_at = now() - timedelta(minutes=1)
        db.commit()

    assert client.post("/api/auth/invitation", json={"token": link_token(mails[0])}).status_code == 400


def test_a_send_failure_returns_502_and_leaves_no_invitation(client, monkeypatch):
    admin = make_user("chef-panne@exemple.fr")

    def broken(to, subject, body):
        raise OSError("SMTP injoignable")

    monkeypatch.setattr("app.account.send_mail", broken)
    response = invite(client, admin, "panne-invit@exemple.fr")

    assert response.status_code == 502
    assert "SMTP" in response.json()["detail"]
    assert client.get("/api/team/invitations", headers=admin.headers).json() == []


def test_invitations_are_rate_limited_per_company(client, mails):
    admin = make_user("chef-debit@exemple.fr")
    statuses = [invite(client, admin, f"debit{n}@exemple.fr").status_code for n in range(21)]
    assert statuses == [200] * 20 + [429]


# --- E-mail ------------------------------------------------------------------


def test_without_smtp_host_the_mail_is_written_to_the_logs(monkeypatch, caplog):
    from app.config import settings
    from app.mailer import send_mail

    monkeypatch.setattr(settings, "smtp_host", "")
    with caplog.at_level(logging.WARNING, logger="app.mailer"):
        send_mail("nina@exemple.fr", "Un objet", "Ouvrez http://localhost:3000/invitation#abc")

    assert "nina@exemple.fr" in caplog.text
    assert "Un objet" in caplog.text
    assert "http://localhost:3000/invitation#abc" in caplog.text


class FakeSMTP:
    """Remplace smtplib.SMTP : note les appels, n'ouvre aucune connexion."""

    calls: list = []

    def __init__(self, host, port, timeout=None):
        self.calls.append(("connect", type(self).__name__, host, port, timeout))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.calls.append(("starttls",))

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.calls.append(("send", message["To"], message["Subject"], message.get_content().strip()))


class FakeSMTPSSL(FakeSMTP):
    pass


@pytest.fixture
def smtp(monkeypatch):
    from app.config import settings

    FakeSMTP.calls = []
    monkeypatch.setattr("app.mailer.smtplib", SimpleNamespace(SMTP=FakeSMTP, SMTP_SSL=FakeSMTPSSL))
    monkeypatch.setattr(settings, "smtp_host", "smtp.exemple.fr")
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_password", "")
    monkeypatch.setattr(settings, "smtp_from", "Sillage <ne-pas-repondre@exemple.fr>")
    return settings


def test_port_587_uses_smtp_with_mandatory_starttls_and_login(monkeypatch, smtp):
    from app.mailer import send_mail

    monkeypatch.setattr(smtp, "smtp_port", 587)
    monkeypatch.setattr(smtp, "smtp_user", "compte")
    monkeypatch.setattr(smtp, "smtp_password", "secret")
    send_mail("nina@exemple.fr", "Objet", "Corps du message")

    assert FakeSMTP.calls == [
        ("connect", "FakeSMTP", "smtp.exemple.fr", 587, 10),
        ("starttls",),
        ("login", "compte", "secret"),
        ("send", "nina@exemple.fr", "Objet", "Corps du message"),
    ]


def test_port_465_uses_smtp_ssl_without_starttls(monkeypatch, smtp):
    from app.mailer import send_mail

    monkeypatch.setattr(smtp, "smtp_port", 465)
    send_mail("nina@exemple.fr", "Objet", "Corps")

    assert FakeSMTP.calls[0] == ("connect", "FakeSMTPSSL", "smtp.exemple.fr", 465, 10)
    assert ("starttls",) not in FakeSMTP.calls


def test_other_ports_stay_plain_and_skip_login_without_a_user(monkeypatch, smtp):
    from app.mailer import send_mail

    monkeypatch.setattr(smtp, "smtp_port", 1025)
    send_mail("nina@exemple.fr", "Objet", "Corps")

    assert [call[0] for call in FakeSMTP.calls] == ["connect", "send"]


def test_smtp_errors_reach_the_caller(monkeypatch, smtp):
    from app.mailer import send_mail

    def refuse(self, message):
        raise OSError("refusé")

    monkeypatch.setattr(FakeSMTP, "send_message", refuse)
    with pytest.raises(OSError):
        send_mail("nina@exemple.fr", "Objet", "Corps")
