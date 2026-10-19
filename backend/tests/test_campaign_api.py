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
    assert "Content-Security-Policy" in public["html"]
    assert public["thanks_html"] == ""  # Le document de merci est protégé jusqu'à la soumission.

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


def test_restoring_an_old_partial_snapshot_keeps_published_fields(client):
    """Les versions créées avant les documents HTML pouvaient être partielles."""
    from app.database import SessionLocal
    from app.models import FormVersion

    form = active_form(client)
    before = client.get(f"/api/forms/{form['id']}").json()
    with SessionLocal() as db:
        version = FormVersion(
            form_id=form["id"], snapshot={"name": "Titre historique"},
            source="manual", message="Ancien instantané",
        )
        db.add(version)
        db.commit()
        version_id = version.id

    restored = client.post(f"/api/forms/{form['id']}/versions/{version_id}/restore")
    assert restored.status_code == 200, restored.text
    payload = restored.json()
    assert payload["draft"]["name"] == "Titre historique"
    for field in before["manifest"]:
        assert f'name="{field["name"]}"' in payload["draft_html"]

    client.post(f"/api/forms/{form['id']}/draft/discard")


def test_metadata_patch_preserves_custom_form_and_updates_legacy_thanks(client):
    campaign = client.post("/api/campaigns", json={"name": "Métadonnées sans perte"}).json()
    form = client.post(
        f"/api/campaigns/{campaign['id']}/forms",
        json={"prompt": "un formulaire de contact simple"},
    ).json()
    custom = '<form data-sillage="form"><h1>Document libre</h1><input name="email"><div data-sillage="consent"></div></form>'
    client.patch(f"/api/forms/{form['id']}/draft", json={"html": custom})
    client.post(f"/api/forms/{form['id']}/draft/publish")
    before = client.get(f"/api/forms/{form['id']}").json()

    changed = client.patch(f"/api/forms/{form['id']}", json={
        "description": "Métadonnée mise à jour",
        "thank_you": {"title": "Autre titre", "message": "Autre message", "action": "none"},
    })
    assert changed.status_code == 200, changed.text
    after = changed.json()
    assert after["description"] == "Métadonnée mise à jour"
    assert after["html"] == before["html"]
    assert "Autre titre" in after["thanks_html"]
    assert "Autre message" in after["thanks_html"]


def test_thank_you_patch_preserves_custom_thanks_document(client):
    from app.database import SessionLocal
    from app.models import Form
    from app.page_document import prepare_page

    campaign = client.post("/api/campaigns", json={"name": "Merci personnalisé"}).json()
    form = client.post(
        f"/api/campaigns/{campaign['id']}/forms",
        json={"prompt": "un formulaire de contact simple"},
    ).json()
    with SessionLocal() as db:
        saved = db.get(Form, form["id"])
        thanks = next(page for page in saved.pages if page.role == "thanks")
        thanks.html, _ = prepare_page('<main><h1>Merci, à bientôt</h1></main>', require_form=False)
        db.commit()

    before = client.get(f"/api/forms/{form['id']}").json()
    changed = client.patch(f"/api/forms/{form['id']}", json={
        "thank_you": {"title": "Autre titre", "message": "Autre message", "action": "none"},
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["thanks_html"] == before["thanks_html"]


def test_thank_you_settings_are_owned_by_tunnel_page(client):
    from app.database import SessionLocal
    from app.models import Form

    campaign = client.post("/api/campaigns", json={"name": "Page de fin dédiée"}).json()
    form = client.post(
        f"/api/campaigns/{campaign['id']}/forms",
        json={"prompt": "un formulaire de contact simple"},
    ).json()
    path = f"/api/forms/{form['id']}/tunnel"
    tunnel = client.get(path).json()
    thanks = next(page for page in tunnel["pages"] if page["role"] == "thanks")
    settings = {
        "title": "Merci pour votre demande",
        "message": "Notre équipe vous répond bientôt.",
        "action": "none",
        "button_label": "Retour au site",
        "button_url": "",
    }

    saved = client.patch(f"{path}/pages/{thanks['id']}", json={"settings": settings})
    assert saved.status_code == 200, saved.text
    saved_page = next(page for page in saved.json()["pages"] if page["id"] == thanks["id"])
    assert saved_page["settings"] == settings
    assert "Merci pour votre demande" in saved_page["html"]
    assert client.get(f"/api/forms/{form['id']}").json()["thank_you"] == settings

    with SessionLocal() as db:
        stored = db.get(Form, form["id"])
        assert stored.thank_you == {}
        assert next(page for page in stored.pages if page.role == "thanks").settings == settings


def test_duplicate_keeps_custom_documents_and_sanitizes_them(client):
    from app.database import SessionLocal
    from app.models import Form, Page
    from app.page_document import prepare_page

    campaign = client.post("/api/campaigns", json={"name": "Duplication fidèle"}).json()
    form = client.post(
        f"/api/campaigns/{campaign['id']}/forms",
        json={"prompt": "un formulaire de contact simple"},
    ).json()
    custom = '<form data-sillage="form"><h1>Composition sur mesure</h1><label>Email<input name="email"></label><div data-sillage="consent"></div></form>'
    client.patch(f"/api/forms/{form['id']}/draft", json={"html": custom})
    client.post(f"/api/forms/{form['id']}/draft/publish")

    with SessionLocal() as db:
        source = db.get(Form, form["id"])
        thanks = next(page for page in source.pages if page.role == "thanks")
        clean_thanks, _ = prepare_page('<main><h1>Merci {prenom}</h1></main>', require_form=False)
        thanks.html = clean_thanks.replace("</body>", '<script>alert(1)</script></body>')
        db.commit()

    duplicated = client.post(f"/api/forms/{form['id']}/duplicate")
    assert duplicated.status_code == 201, duplicated.text
    copy = duplicated.json()
    assert "Composition sur mesure" in copy["html"]
    assert copy["manifest"] == [{"id": "email", "name": "email", "type": "text", "label": "Email", "required": False}]
    assert "Merci" in copy["thanks_html"]
    assert "<script" not in copy["thanks_html"] and "alert(1)" not in copy["thanks_html"]

    with SessionLocal() as db:
        copied = db.get(Form, copy["id"])
        copied_thanks = db.get(Page, next(page.id for page in copied.pages if page.role == "thanks"))
        assert "{prenom}" in copied_thanks.html
        assert copied.pages[0].visits == 0 and copied_thanks.visits == 0


def test_a_visit_is_counted_only_when_the_browser_says_so(client):
    form = active_form(client)
    before = client.get(f"/api/forms/{form['id']}").json()["visits"]

    client.get(f"/api/public/{form['slug']}")
    client.get(f"/api/public/{form['slug']}")
    assert client.get(f"/api/forms/{form['id']}").json()["visits"] == before

    client.post(f"/api/public/{form['slug']}/visit")
    assert client.get(f"/api/forms/{form['id']}").json()["visits"] == before + 1


def test_tunnel_pages_and_public_journey_are_scoped(client):
    campaign = client.post("/api/campaigns", json={"name": "Parcours protégé"}).json()
    form = client.post(f"/api/campaigns/{campaign['id']}/forms", json={"prompt": "un formulaire de contact simple"}).json()
    form_id, slug = form["id"], form["slug"]
    base = f"/api/forms/{form_id}/tunnel"
    original = client.get(base).json()
    assert [page["role"] for page in original["pages"]] == ["form", "thanks"]
    assert original["entry_page_id"] == form_id

    created = client.post(f"{base}/pages", json={"role": "landing", "name": "Accueil"})
    assert created.status_code == 201, created.text
    tunnel = created.json()
    landing = tunnel["pages"][0]
    assert landing["role"] == "landing" and tunnel["entry_page_id"] == landing["id"]
    assert landing["next_page_id"] == form_id
    assert "data-sillage-next" in landing["html"]

    other = client.post(f"/api/campaigns/{campaign['id']}/forms", json={"prompt": "un deuxième formulaire simple"}).json()
    target = client.patch(f"{base}/pages/{landing['id']}", json={"next_page_id": other["id"]})
    assert target.status_code == 422
    assert client.patch(f"{base}/pages/{landing['id']}", json={"next_page_id": original["pages"][1]["id"]}).status_code == 422
    assert client.patch(f"{base}/pages/{original['pages'][1]['id']}", json={"position": 0}).status_code == 422
    loop = client.patch(f"{base}/pages/{form_id}", json={"next_page_id": landing["id"]})
    assert loop.status_code == 422

    public = client.get(f"/api/public/{slug}").json()
    assert public["tunnel"]["entry_page_id"] == landing["id"]
    assert public["thanks_html"] == ""
    assert "Accueil" in public["html"]
    assert all("html" not in page for page in public["tunnel"]["pages"])

    client.patch(f"/api/forms/{form_id}", json={"status": "active"})
    unentered = client.post(f"/api/public/{slug}/advance", json={"from_page_id": landing["id"]})
    assert unentered.status_code == 403
    assert client.post(f"/api/public/{slug}/visit", json={"page_id": original["pages"][1]["id"]}).status_code == 403
    entered = client.post(f"/api/public/{slug}/visit", json={"page_id": landing["id"]})
    assert entered.status_code == 200, entered.text
    advanced = client.post(f"/api/public/{slug}/advance", json={"from_page_id": landing["id"]})
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["page_id"] == form_id
    assert client.get(base).json()["pages"][0]["conversions"] == 1
    assert client.post(f"/api/public/{slug}/advance", json={"from_page_id": landing["id"]}).status_code == 403
    # La page de merci ne s'ouvre qu'après une soumission valide.
    assert client.post(f"/api/public/{slug}/advance", json={"from_page_id": form_id}).status_code == 422

    manifest = advanced.json()["manifest"]
    answers = {field["name"]: "Alice" for field in manifest if field.get("required")}
    sent = client.post(f"/api/public/{slug}/submit", json={"page_id": form_id, "answers": answers, "consent": True})
    assert sent.status_code == 201, sent.text
    assert sent.json()["next_page_id"] == original["pages"][1]["id"]
    assert "Content-Security-Policy" in sent.json()["thanks_html"]
    assert client.post(f"/api/public/{slug}/submit", json={"page_id": form_id, "answers": answers, "consent": True}).status_code == 403
    thanks = client.post(f"/api/public/{slug}/visit", json={"page_id": sent.json()["next_page_id"]})
    assert thanks.status_code == 200


def test_reordering_tunnel_pages_updates_the_public_journey(client):
    campaign = client.post("/api/campaigns", json={"name": "Ordre du parcours"}).json()
    form = client.post(f"/api/campaigns/{campaign['id']}/forms", json={"prompt": "un formulaire de contact simple"}).json()
    client.patch(f"/api/forms/{form['id']}", json={"status": "active"})
    path = f"/api/forms/{form['id']}/tunnel"

    created = client.post(f"{path}/pages", json={"role": "landing", "name": "Présentation"})
    assert created.status_code == 201, created.text
    landing = next(page for page in created.json()["pages"] if page["name"] == "Présentation")
    reordered = client.patch(f"{path}/pages/{landing['id']}", json={"position": 1})
    assert reordered.status_code == 200, reordered.text
    tunnel = reordered.json()
    pages = sorted(tunnel["pages"], key=lambda page: page["position"])
    by_id = {page["id"]: page for page in pages}
    thanks = next(page for page in pages if page["role"] == "thanks")
    assert [page["role"] for page in pages] == ["form", "landing", "thanks"]
    assert tunnel["entry_page_id"] == form["id"]
    assert by_id[form["id"]]["next_page_id"] == landing["id"]
    assert by_id[landing["id"]]["next_page_id"] == thanks["id"]

    slug = form["slug"]
    assert client.post(f"/api/public/{slug}/visit", json={"page_id": form["id"]}).status_code == 200
    form_page = client.get(f"/api/public/{slug}", params={"page_id": form["id"]}).json()
    answers = {field["name"]: "Alice" for field in form_page["manifest"] if field.get("required") and field["type"] != "consent"}
    submitted = client.post(f"/api/public/{slug}/submit", json={
        "page_id": form["id"], "answers": answers, "consent": True,
    })
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["next_page_id"] == landing["id"]

    advanced = client.post(f"/api/public/{slug}/advance", json={"from_page_id": landing["id"]})
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["page_id"] == thanks["id"]
    assert advanced.json()["role"] == "thanks"


def test_tunnel_page_create_supports_blank_templates_and_page_previews(client):
    campaign = client.post("/api/campaigns", json={"name": "Modèles de pages"}).json()
    rejected_site = client.post(f"/api/campaigns/{campaign['id']}/forms", json={
        "prompt": "un formulaire de contact simple", "website_url": "http://atelier.example",
    })
    assert rejected_site.status_code == 422
    form = client.post(f"/api/campaigns/{campaign['id']}/forms", json={"prompt": "un formulaire de contact simple"}).json()
    path = f"/api/forms/{form['id']}/tunnel"

    source = client.post(f"{path}/pages", json={"role": "landing", "name": "Page source"})
    assert source.status_code == 201, source.text
    source_page = next(page for page in source.json()["pages"] if page["name"] == "Page source")

    copied = client.post(f"{path}/pages", json={
        "role": "landing", "name": "Page modèle copiée", "template_page_id": source_page["id"],
    })
    assert copied.status_code == 201, copied.text
    copy_page = next(page for page in copied.json()["pages"] if page["name"] == "Page modèle copiée")
    assert copy_page["html"] == source_page["html"]
    assert copy_page["slug"] == "page-modele-copiee"
    assert copied.json()["entry_page_id"] == copy_page["id"]

    blank = client.post(f"{path}/pages", json={"role": "form", "name": "Collecte vierge"})
    assert blank.status_code == 201, blank.text
    blank_page = next(page for page in blank.json()["pages"] if page["name"] == "Collecte vierge")
    assert '<form data-sillage="form"' in blank_page["html"]
    assert 'data-sillage="consent"' in blank_page["html"]
    assert "<h1 data-luna-id=\"title\">Collecte vierge</h1>" in blank_page["html"]
    assert blank_page["next_page_id"]

    preview = client.get(f"/api/public/{form['slug']}", params={"page_id": blank_page["id"]})
    assert preview.status_code == 200, preview.text
    assert preview.json()["current_page_id"] == blank_page["id"]
    assert '<form data-sillage="form"' in preview.json()["html"]
    assert preview.json()["manifest"] == []

    entered_first = client.patch(f"{path}/pages/{blank_page['id']}", json={"position": 0})
    assert entered_first.status_code == 200, entered_first.text
    assert entered_first.json()["entry_page_id"] == blank_page["id"]
    client.patch(f"/api/forms/{form['id']}", json={"status": "active"})
    empty_submit = client.post(f"/api/public/{form['slug']}/submit", json={
        "page_id": blank_page["id"], "answers": {}, "consent": True,
    })
    assert empty_submit.status_code == 422
    assert "Ajoutez au moins un champ" in empty_submit.json()["detail"]

    renamed = client.patch(f"{path}/pages/{copy_page['id']}", json={"name": "Nouvelle présentation"})
    assert renamed.status_code == 200, renamed.text
    renamed_page = next(page for page in renamed.json()["pages"] if page["id"] == copy_page["id"])
    assert renamed_page["name"] == "Nouvelle présentation"

    other = client.post(f"/api/campaigns/{campaign['id']}/forms", json={"prompt": "un autre formulaire simple"}).json()
    other_path = f"/api/forms/{other['id']}/tunnel"
    cross_tunnel = client.post(f"{other_path}/pages", json={
        "role": "landing", "name": "Modèle externe", "template_page_id": source_page["id"],
    })
    assert cross_tunnel.status_code == 422


def test_luna_can_edit_and_publish_a_tunnel_landing(client, monkeypatch):
    from app import main
    from app.config import settings

    campaign = client.post("/api/campaigns", json={"name": "Page Luna"}).json()
    form = client.post(f"/api/campaigns/{campaign['id']}/forms", json={"prompt": "un formulaire de contact simple"}).json()
    path = f"/api/forms/{form['id']}/tunnel"
    landing = client.post(f"{path}/pages", json={"role": "landing", "name": "Accueil"}).json()["pages"][0]
    original = landing["html"]
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    def fake_revision(html, instruction, identity, **kwargs):
        assert kwargs["selection"]["page_role"] == "landing"
        return {"message": "Accueil mis à jour.", "html": html.replace("Bienvenue", "Bonjour").replace("Accueil", "Bonjour"), "region": None}

    monkeypatch.setattr(main, "revise_page", fake_revision)
    revised = client.post(f"/api/forms/{form['id']}/luna/refine", json={
        "instruction": "Change le titre", "page_id": landing["id"],
    })
    assert revised.status_code == 200, revised.text
    draft = client.get(path).json()["pages"][0]["html"]
    assert "Bonjour" in draft and "Bonjour" not in original
    assert "Accueil" in client.get(f"/api/public/{form['slug']}").json()["html"]
    published = client.post(f"/api/forms/{form['id']}/draft/publish")
    assert published.status_code == 200, published.text
    assert "Bonjour" in client.get(f"/api/public/{form['slug']}").json()["html"]
    history = client.get(f"/api/forms/{form['id']}/versions").json()
    initial = next(version for version in history if version["source"] == "initial" and version["page_id"] == landing["id"])
    restored = client.post(f"/api/forms/{form['id']}/versions/{initial['id']}/restore")
    assert restored.status_code == 200, restored.text
    assert "Accueil" in client.get(path).json()["pages"][0]["html"]
    assert "Bonjour" in client.get(f"/api/public/{form['slug']}").json()["html"]


def test_duplicate_preserves_tunnel_order_and_links(client):
    campaign = client.post("/api/campaigns", json={"name": "Copie de tunnel"}).json()
    form = client.post(f"/api/campaigns/{campaign['id']}/forms", json={"prompt": "un formulaire de contact simple"}).json()
    path = f"/api/forms/{form['id']}/tunnel"
    client.post(f"{path}/pages", json={"role": "landing", "name": "Bienvenue"})
    client.post(f"{path}/pages", json={"role": "form"})
    source = client.get(path).json()
    duplicated = client.post(f"/api/forms/{form['id']}/duplicate")
    assert duplicated.status_code == 201, duplicated.text
    target = client.get(f"/api/forms/{duplicated.json()['id']}/tunnel").json()
    assert [item["role"] for item in target["pages"]] == [item["role"] for item in source["pages"]]
    assert [item["visits"] for item in target["pages"]] == [0] * len(target["pages"])
    assert target["entry_page_id"] == target["pages"][0]["id"]
    assert target["pages"][0]["next_page_id"] == target["pages"][1]["id"]


def test_tunnel_routes_reject_another_company(client):
    from app.database import SessionLocal
    from app.models import Company, User
    from app.security import hash_password

    form = active_form(client)
    with SessionLocal() as db:
        company = Company(name="Autre société")
        db.add(company)
        db.flush()
        db.add(User(company_id=company.id, email="other@example.org", full_name="Autre", password_hash=hash_password("test-password")))
        db.commit()
    login = client.post("/api/auth/login", json={"email": "other@example.org", "password": "test-password"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/api/forms/{form['id']}/tunnel"
    assert client.get(path, headers=headers).status_code == 404
    assert client.post(f"{path}/pages", headers=headers, json={"role": "landing"}).status_code == 404


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

    def fake_revision(html, instruction, identity, **kwargs):
        assert kwargs["selection"]["element_ids"] == ["submit"]
        assert "brief" in kwargs
        assert "visits" in kwargs["stats"]
        assert "email" in kwargs["existing_names"]
        return {
            "message": "Bouton renommé.",
            "html": html.replace("</form>", '<p>Être rappelé</p></form>'),
            "region": None,
        }

    monkeypatch.setattr(main, "revise_page", fake_revision)
    response = client.post(f"/api/forms/{form['id']}/luna/refine", json={
        "instruction": "Renomme le bouton",
        "element_ids": ["submit"],
        "selection_label": "le bouton",
        "view": "form",
    })
    assert response.status_code == 200, response.text
    result = response.json()

    assert result["touched"] == []
    assert "Être rappelé" in result["form"]["draft_html"]
    assert "Être rappelé" not in result["form"]["html"]

    versions = client.get(f"/api/forms/{form['id']}/versions").json()
    assert versions[-1]["instruction"] == "Renomme le bouton"
    assert versions[-1]["message"] == "Bouton renommé."

    client.post(f"/api/forms/{form['id']}/draft/discard")


def test_luna_creation_stores_a_free_document_when_connected(client, monkeypatch):
    from app import main
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    document = ('<!doctype html><html><head><style>body{background:#123}</style></head><body>'
                '<main data-sillage-region="hero"><h1>Une page libre</h1><p>Trois arguments</p></main>'
                '<form data-sillage="form"><label>Email<input name="email" type="email" required></label>'
                '<div data-sillage="consent"></div><button>Envoyer</button></form></body></html>')
    def generate_page(*args, **kwargs):
        assert kwargs["form_name"] == "Contact personnalisé"
        assert kwargs["description"] == "Une demande pour être rappelé."
        assert kwargs["website_url"] == "https://atelier.example/"
        return {"message": "Page créée", "html": document, "region": None}

    monkeypatch.setattr(main, "generate_page", generate_page)
    campaign = client.post("/api/campaigns", json={"name": "Page libre"}).json()
    created = client.post(f"/api/campaigns/{campaign['id']}/forms", json={
        "prompt": "Une vitrine avec un formulaire en bas",
        "name": "Contact personnalisé",
        "description": "Une demande pour être rappelé.",
        "website_url": "https://atelier.example",
    })
    assert created.status_code == 201, created.text
    form = created.json()
    assert "Une page libre" in form["html"]
    assert "Trois arguments" in form["html"]
    assert [field["name"] for field in form["manifest"]] == ["email"]
    assert form["name"] == "Contact personnalisé"


def test_luna_stream_previews_then_stores_only_the_validated_page(client, monkeypatch):
    import json

    from app import main
    from app.config import settings

    form = active_form(client)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    def fake_stream(html, instruction, identity, **kwargs):
        yield {"type": "preview", "html": "<main><h1>En cours", "region": None}
        yield {"type": "final", "message": "Page terminée.", "html": html.replace("</form>", '<p>Page terminée</p></form>'), "region": None}

    monkeypatch.setattr(main, "stream_page_revision", fake_stream)
    response = client.post(f"/api/forms/{form['id']}/luna/refine/stream", json={"instruction": "Ajoute un message en bas"})
    assert response.status_code == 200, response.text
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert [event["type"] for event in events] == ["preview", "final"]
    assert "Page terminée" in events[-1]["form"]["draft_html"]
    assert "En cours" not in events[-1]["form"]["draft_html"]
    assert events[-1]["version"]["message"] == "Page terminée."


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


def test_submit_returns_safely_personalized_thanks_html(client):
    from app.database import SessionLocal
    from app.models import Form
    from app.page_document import prepare_page

    campaign = client.post("/api/campaigns", json={"name": "Merci personnalisé"}).json()
    form = client.post(
        f"/api/campaigns/{campaign['id']}/forms",
        json={"prompt": "un formulaire de contact simple"},
    ).json()
    client.patch(f"/api/forms/{form['id']}", json={"status": "active"})
    with SessionLocal() as db:
        stored = db.get(Form, form["id"])
        thanks = next(page for page in stored.pages if page.role == "thanks")
        thanks.html, _ = prepare_page('<main><h1>Merci {prenom} !</h1></main>', require_form=False)
        db.commit()

    answers = {}
    for field in form["manifest"]:
        if field["required"]:
            answers[field["name"]] = "valeur"
    answers["name"] = "<Noémie> Martin"
    submitted = client.post(
        f"/api/public/{form['slug']}/submit",
        json={"answers": answers, "consent": True},
    )
    assert submitted.status_code == 201, submitted.text
    thanks_html = submitted.json()["thanks_html"]
    assert "Merci &lt;Noémie&gt; !" in thanks_html
    assert "<Noémie>" not in thanks_html and "{prenom}" not in thanks_html
    assert "Content-Security-Policy" in thanks_html


def test_html_draft_warns_about_old_answers_and_preserves_them(client):
    campaign = client.post("/api/campaigns", json={"name": "Demandes HTML"}).json()
    form = client.post(f"/api/campaigns/{campaign['id']}/forms", json={"prompt": "un formulaire de contact simple"}).json()
    client.patch(f"/api/forms/{form['id']}", json={"status": "active"})
    answers = {field["id"]: "Valeur" for field in form["fields"] if field.get("required") and field["type"] != "consent"}
    assert client.post(f"/api/public/{form['slug']}/submit", json={"answers": answers, "consent": True}).status_code == 201

    html = '<style>body{background:#fff}</style><form data-sillage="form"><label for="new_name">Nouveau nom</label><input id="new_name" name="new_name" required><div data-sillage="consent">Texte de Luna</div><button>Envoyer</button></form><script>alert(1)</script>'
    edited = client.patch(f"/api/forms/{form['id']}/draft", json={"html": html})
    assert edited.status_code == 200, edited.text
    assert edited.json()["field_warnings"]
    assert "<script" not in edited.json()["draft_html"]
    assert "Texte de Luna" not in edited.json()["draft_html"]

    public_before = client.get(f"/api/public/{form['slug']}").json()
    assert "new_name" not in public_before["manifest"][0]["name"]
    assert client.post(f"/api/forms/{form['id']}/draft/publish").status_code == 200
    public_after = client.get(f"/api/public/{form['slug']}").json()
    assert public_after["manifest"][0]["name"] == "new_name"
    assert "J'accepte" in public_after["html"]
    published = client.get(f"/api/forms/{form['id']}").json()
    assert [field["name"] for field in published["fields"] if field["type"] != "consent"] == ["new_name"]

    # Une retouche ultérieure qui repasse par le convertisseur ne doit pas
    # ressusciter les anciens champs conservés seulement dans les réponses.
    redrafted = client.patch(f"/api/forms/{form['id']}/draft", json={"description": "Nouvelle description"}).json()
    for old_name in answers:
        assert f'name="{old_name}"' not in redrafted["draft_html"]
    client.cookies.clear()  # Nouvelle visite après la réponse déjà envoyée.
    assert client.post(f"/api/public/{form['slug']}/submit", json={"answers": answers, "consent": True}).status_code == 422
    assert client.post(f"/api/public/{form['slug']}/submit", json={"answers": {"new_name": "Alice"}, "consent": True}).status_code == 201
    inbox = client.get("/api/responses", params={"form_id": form["id"]}).json()
    assert inbox["total"] == 2
    assert any(row["answers"] == answers for row in inbox["items"])
    client.post(f"/api/forms/{form['id']}/draft/discard")
