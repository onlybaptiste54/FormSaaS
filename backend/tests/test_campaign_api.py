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


def all_forms(client):
    forms = []
    for campaign in client.get("/api/campaigns").json():
        forms += client.get(f"/api/campaigns/{campaign['id']}/forms").json()
    return forms


def active_form(client):
    return next(f for f in all_forms(client) if f["status"] == "active")


def test_a_campaign_gathers_several_forms(client):
    campaigns = client.get("/api/campaigns").json()
    assert len(campaigns) == 2
    biggest = max(campaigns, key=lambda c: c["forms"])
    assert biggest["forms"] == 2
    assert biggest["responses"] == sum(f["responses"] for f in client.get(f"/api/campaigns/{biggest['id']}/forms").json())


def test_a_form_is_always_created_inside_a_campaign(client):
    campaign = client.post("/api/campaigns", json={"name": "Salon de printemps", "client": "Atelier Rivage"}).json()
    assert campaign["forms"] == 0

    form = client.post(f"/api/campaigns/{campaign['id']}/forms", json={"prompt": "un formulaire de contact simple", "name": "Contact salon"}).json()
    assert form["campaign_id"] == campaign["id"]
    assert form["name"] == "Contact salon"
    assert client.get(f"/api/campaigns/{campaign['id']}").json()["forms"] == 1

    # Deux campagnes peuvent porter un formulaire du meme nom : le lien reste unique.
    other = client.post(f"/api/campaigns/{campaign['id']}/forms", json={"prompt": "un formulaire de contact simple", "name": "Contact salon"}).json()
    assert other["slug"] != form["slug"]


def test_campaign_stats_aggregate_its_forms(client):
    campaign = max(client.get("/api/campaigns").json(), key=lambda c: c["responses"])
    stats = client.get(f"/api/campaigns/{campaign['id']}/stats").json()
    assert stats["forms"] == 2
    assert stats["responses"] == sum(row["responses"] for row in stats["breakdown"])
    assert stats["best"]["responses"] == max(row["responses"] for row in stats["breakdown"])


def test_draft_is_separate_from_the_published_form(client):
    form = active_form(client)
    published_name = form["name"]

    updated = client.patch(f"/api/forms/{form['id']}/draft", json={"name": "Titre en préparation"}).json()
    assert updated["name"] == published_name
    assert updated["draft"]["name"] == "Titre en préparation"

    public = client.get(f"/api/public/{form['slug']}").json()
    assert public["name"] == published_name

    published = client.post(f"/api/forms/{form['id']}/draft/publish").json()
    assert published["name"] == "Titre en préparation"
    assert published["draft"] is None
    assert client.get(f"/api/public/{form['slug']}").json()["name"] == "Titre en préparation"


def test_restoring_a_version_brings_back_the_previous_state(client):
    form = active_form(client)
    client.patch(f"/api/forms/{form['id']}/draft", json={"description": "Première version"})
    client.post(f"/api/forms/{form['id']}/draft/publish")
    client.patch(f"/api/forms/{form['id']}/draft", json={"description": "Deuxième version"})

    # L'historique ne renvoie pas les instantanes : on vise la version publiee.
    versions = client.get(f"/api/forms/{form['id']}/versions").json()
    published_version = next(version for version in reversed(versions) if version["source"] == "publish")
    restored = client.post(f"/api/forms/{form['id']}/versions/{published_version['id']}/restore").json()
    assert restored["draft"]["description"] == "Première version"

    client.post(f"/api/forms/{form['id']}/draft/discard")
    assert client.get(f"/api/forms/{form['id']}").json()["draft"] is None


def test_a_visit_is_counted_only_when_the_browser_says_so(client):
    form = active_form(client)
    before = client.get(f"/api/forms/{form['id']}").json()["visits"]

    client.get(f"/api/public/{form['slug']}")
    client.get(f"/api/public/{form['slug']}")
    assert client.get(f"/api/forms/{form['id']}").json()["visits"] == before

    client.post(f"/api/public/{form['slug']}/visit")
    assert client.get(f"/api/forms/{form['id']}").json()["visits"] == before + 1


def test_thank_you_url_must_be_https(client):
    form = active_form(client)
    refused = client.patch(f"/api/forms/{form['id']}", json={
        "thank_you": {"title": "Merci", "message": "Bien reçu", "action": "cta", "button_label": "Voir", "button_url": "http://exemple.fr"},
    })
    assert refused.status_code == 422


def test_the_inbox_filters_by_campaign_form_source_and_text(client):
    forms = all_forms(client)
    survey = next(f for f in forms if f["kind"] == "survey")
    everything = client.get("/api/responses").json()
    assert everything["total"] == sum(f["responses"] for f in forms)
    assert everything["items"][0]["campaign"] and everything["items"][0]["form"]

    by_campaign = client.get("/api/responses", params={"campaign_id": survey["campaign_id"]}).json()
    assert by_campaign["total"] == sum(f["responses"] for f in forms if f["campaign_id"] == survey["campaign_id"])

    by_form = client.get("/api/responses", params={"form_id": survey["id"]}).json()
    assert by_form["total"] == survey["responses"]
    assert all(item["form_id"] == survey["id"] for item in by_form["items"])

    source = everything["sources"][0]
    assert all(item["source"] == source for item in client.get("/api/responses", params={"source": source}).json()["items"])

    found = client.get("/api/responses", params={"q": "Léa Bernard"}).json()
    assert found["total"] and all("Léa" in str(item["answers"]) for item in found["items"])

    page = client.get("/api/responses", params={"limit": 5, "offset": 5}).json()
    assert len(page["items"]) == 5 and page["total"] == everything["total"]


def test_archiving_a_campaign_hides_its_forms_without_losing_responses(client):
    campaign = max(client.get("/api/campaigns").json(), key=lambda c: c["responses"])
    before = client.get("/api/stats").json()
    kept = client.get("/api/responses").json()["total"]

    client.patch(f"/api/campaigns/{campaign['id']}", json={"archived": True})
    after = client.get("/api/stats").json()
    assert after["responses"] == before["responses"] - campaign["responses"]
    assert after["campaigns"] == before["campaigns"] - 1
    # Les reponses restent consultables : rien n'est supprime.
    assert client.get("/api/responses").json()["total"] == kept

    client.patch(f"/api/campaigns/{campaign['id']}", json={"archived": False})
    assert client.get("/api/stats").json()["responses"] == before["responses"]


def test_luna_revision_lands_in_the_draft_with_its_version(client, monkeypatch):
    from app import main
    from app.config import settings

    form = active_form(client)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    def fake_revision(state, instruction, identity, **kwargs):
        assert kwargs["selection"]["element_ids"] == ["submit"]
        return {
            **state,
            "content": {**state["content"], "submit_label": "Être rappelé"},
            "assistant_message": "Bouton renommé.",
            "touched": ["submit"],
            "ops": [{"op": "set_text", "target": "submit_label", "value": "Être rappelé"}],
        }

    monkeypatch.setattr(main, "revise_campaign", fake_revision)
    result = client.post(f"/api/forms/{form['id']}/luna/refine", json={
        "instruction": "Renomme le bouton",
        "element_ids": ["submit"],
        "selection_label": "le bouton",
        "view": "form",
    }).json()

    assert result["touched"] == ["submit"]
    assert result["form"]["draft"]["content"]["submit_label"] == "Être rappelé"
    assert result["form"]["content"]["submit_label"] != "Être rappelé"

    versions = client.get(f"/api/forms/{form['id']}/versions").json()
    assert versions[-1]["instruction"] == "Renomme le bouton"
    assert versions[-1]["message"] == "Bouton renommé."

    client.post(f"/api/forms/{form['id']}/draft/discard")


def test_a_public_answer_lands_in_the_inbox_of_its_campaign(client):
    campaign = client.post("/api/campaigns", json={"name": "Boutique de Noël"}).json()
    form = client.post(f"/api/campaigns/{campaign['id']}/forms", json={"prompt": "un formulaire de contact simple"}).json()
    client.patch(f"/api/forms/{form['id']}", json={"status": "active"})

    consent = next(field for field in form["fields"] if field["type"] == "consent")
    answers = {field["id"]: "Noémie Vasseur" for field in form["fields"] if field["required"] and field["type"] != "consent"}
    created = client.post(f"/api/public/{form['slug']}/submit", json={"answers": answers, "source": "QR Code", "consent": True})
    assert created.status_code == 201

    inbox = client.get("/api/responses", params={"campaign_id": campaign["id"]}).json()
    assert inbox["total"] == 1
    row = inbox["items"][0]
    assert row["campaign"] == "Boutique de Noël" and row["form"] == form["name"]
    assert row["source"] == "QR Code" and row["consent"] is True and row["consent_text"] == consent["label"]

    # La recherche plein texte trouve un accent, et l'export reprend le meme filtre.
    assert client.get("/api/responses", params={"campaign_id": campaign["id"], "q": "Noémie"}).json()["total"] == 1
    export = client.get("/api/responses/export.csv", params={"campaign_id": campaign["id"]})
    assert export.status_code == 200 and "Boutique de Noël" in export.text

    client.patch(f"/api/campaigns/{campaign['id']}", json={"archived": True})
    # Une campagne archivee ne repond plus : le lien public est ferme.
    assert client.post(f"/api/public/{form['slug']}/submit", json={"answers": answers, "consent": True}).status_code == 404
    assert client.get(f"/api/public/{form['slug']}").status_code == 404
    client.patch(f"/api/campaigns/{campaign['id']}", json={"archived": False})
