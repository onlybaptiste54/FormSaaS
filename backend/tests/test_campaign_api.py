import os
import tempfile

import pytest


@pytest.fixture(scope="module")
def client():
    """API complete sur une base SQLite jetable, donnees de demonstration incluses."""
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        token = test_client.post("/api/auth/login", json={"email": "demo@sillage.fr", "password": "demo1234"}).json()["access_token"]
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client

    # Windows garde le fichier ouvert tant que le moteur vit.
    from app.database import engine

    engine.dispose()
    os.unlink(path)


def active_campaign(client):
    return next(c for c in client.get("/api/campaigns").json() if c["status"] == "active")


def test_draft_is_separate_from_the_published_form(client):
    campaign = active_campaign(client)
    published_name = campaign["name"]

    updated = client.patch(f"/api/campaigns/{campaign['id']}/draft", json={"name": "Titre en préparation"}).json()
    assert updated["name"] == published_name
    assert updated["draft"]["name"] == "Titre en préparation"

    public = client.get(f"/api/public/{campaign['slug']}").json()
    assert public["name"] == published_name

    published = client.post(f"/api/campaigns/{campaign['id']}/draft/publish").json()
    assert published["name"] == "Titre en préparation"
    assert published["draft"] is None
    assert client.get(f"/api/public/{campaign['slug']}").json()["name"] == "Titre en préparation"


def test_restoring_a_version_brings_back_the_previous_state(client):
    campaign = active_campaign(client)
    client.patch(f"/api/campaigns/{campaign['id']}/draft", json={"description": "Première version"})
    client.post(f"/api/campaigns/{campaign['id']}/draft/publish")
    client.patch(f"/api/campaigns/{campaign['id']}/draft", json={"description": "Deuxième version"})

    # L'historique ne renvoie pas les instantanes : on vise la version publiee.
    versions = client.get(f"/api/campaigns/{campaign['id']}/versions").json()
    published_version = next(version for version in reversed(versions) if version["source"] == "publish")
    restored = client.post(f"/api/campaigns/{campaign['id']}/versions/{published_version['id']}/restore").json()
    assert restored["draft"]["description"] == "Première version"

    client.post(f"/api/campaigns/{campaign['id']}/draft/discard")
    assert client.get(f"/api/campaigns/{campaign['id']}").json()["draft"] is None


def test_a_visit_is_counted_only_when_the_browser_says_so(client):
    campaign = active_campaign(client)
    before = client.get(f"/api/campaigns/{campaign['id']}").json()["visits"]

    client.get(f"/api/public/{campaign['slug']}")
    client.get(f"/api/public/{campaign['slug']}")
    assert client.get(f"/api/campaigns/{campaign['id']}").json()["visits"] == before

    client.post(f"/api/public/{campaign['slug']}/visit")
    assert client.get(f"/api/campaigns/{campaign['id']}").json()["visits"] == before + 1


def test_thank_you_url_must_be_https(client):
    campaign = active_campaign(client)
    refused = client.patch(f"/api/campaigns/{campaign['id']}", json={
        "thank_you": {"title": "Merci", "message": "Bien reçu", "action": "cta", "button_label": "Voir", "button_url": "http://exemple.fr"},
    })
    assert refused.status_code == 422
