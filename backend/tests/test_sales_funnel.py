import os
import tempfile
import io
import zipfile

import pytest


@pytest.fixture(scope="module")
def client():
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as test_client:
        token = test_client.post("/api/auth/login", json={"email": "demo@sillage.fr", "password": "demo1234"}).json()["access_token"]
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client

    from app.database import engine
    engine.dispose()
    os.unlink(path)


def brief():
    return {"name": "Accompagnement commercial", "offer": "Un accompagnement de six semaines pour structurer la prospection.",
            "audience": "Les indépendants qui cherchent leurs premiers clients réguliers.",
            "benefits": ["Un diagnostic individuel", "Un suivi hebdomadaire"],
            "proof": "", "tone": "Direct et chaleureux", "goal_label": "Réserver un appel",
            "goal_url": "https://example.com/reserver", "website_url": ""}


def fake_page(html, instruction, identity, **kwargs):
    role = kwargs["selection"]["page_role"]
    action = "data-sillage-next" if role == "landing" else "data-sillage-goal"
    suffix = " modifié" if html else ""
    return {"message": "Page prête", "region": None,
            "html": f'<!doctype html><html><head><style>body{{color:#111}}</style></head><body><main><h1>{role}{suffix}</h1><button type="button" {action}>Continuer</button></main></body></html>'}


def test_guided_funnel_publication_and_measured_journey(client, monkeypatch):
    from app import sales

    monkeypatch.setattr(sales.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(sales, "revise_page", fake_page)
    created = client.post("/api/sales-funnels", json=brief())
    assert created.status_code == 201, created.text
    tunnel = created.json()
    assert tunnel["kind"] == "sales"
    assert tunnel["status"] == "draft"
    assert [page["role"] for page in tunnel["pages"]] == ["landing", "offer"]
    slug = tunnel["slug"]
    assert client.post(f"/api/public/sales/{slug}/visit", json={"source": "Email"}).status_code == 404

    published = client.post(f"/api/sales-funnels/{tunnel['id']}/publish")
    assert published.status_code == 200
    first = client.post(f"/api/public/sales/{slug}/visit", json={"source": "Email"})
    assert first.status_code == 200, first.text
    assert first.json()["role"] == "landing"
    assert client.post(f"/api/public/sales/{slug}/visit", json={"source": "Réseaux sociaux"}).json()["role"] == "landing"
    second = client.post(f"/api/public/sales/{slug}/advance")
    assert second.status_code == 200
    assert second.json()["role"] == "offer"
    goal = client.post(f"/api/public/sales/{slug}/goal")
    assert goal.status_code == 200
    assert goal.json()["url"] == brief()["goal_url"]
    assert client.post(f"/api/public/sales/{slug}/goal").status_code == 200
    stats = client.get(f"/api/sales-funnels/{tunnel['id']}/stats").json()
    assert stats["visits"] == 1
    assert stats["goals"] == 1
    assert stats["conversion"] == 100.0
    assert stats["sources"] == [{"source": "Email", "visits": 1, "goals": 1}]
    assert [page["visits"] for page in stats["pages"]] == [1, 1]
    assert stats["daily"][-1]["visits"] == 1
    overview = client.get("/api/sales-funnels/overview").json()
    assert overview["active"] >= 1
    assert overview["visits"] == 1
    assert overview["goals"] == 1
    updated = client.patch(f"/api/sales-funnels/{tunnel['id']}/destination",
                           json={"goal_url": "https://example.com/nouveau"})
    assert updated.status_code == 200
    assert client.post(f"/api/public/sales/{slug}/goal").json()["url"] == "https://example.com/nouveau"
    assert client.patch(f"/api/sales-funnels/{tunnel['id']}/destination",
                        json={"goal_url": "http://example.com"}).status_code == 422
    exported = client.get(f"/api/sales-funnels/{tunnel['id']}/export.zip")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert set(archive.namelist()) == {"index.html", "offre.html", "LISEZ-MOI.txt"}
        assert "offre.html" in archive.read("index.html").decode()
        assert "https://example.com/nouveau" in archive.read("offre.html").decode()


def test_refine_keeps_public_page_until_publish_and_can_restore(client, monkeypatch):
    from app import sales

    monkeypatch.setattr(sales.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(sales, "revise_page", fake_page)
    tunnel = client.post("/api/sales-funnels", json={**brief(), "name": "Offre de conseil"}).json()
    tunnel_id = tunnel["id"]
    page_id = tunnel["entry_page_id"]
    client.post(f"/api/sales-funnels/{tunnel_id}/publish")
    refined = client.post(f"/api/sales-funnels/{tunnel_id}/pages/{page_id}/refine", json={"instruction": "Ajuste le titre"})
    assert refined.status_code == 200, refined.text
    assert refined.json()["changed"] is True
    assert refined.json()["tunnel"]["pages"][0]["has_draft"] is True
    assert "modifié" not in client.post(f"/api/public/sales/{tunnel['slug']}/visit", json={}).json()["html"]
    client.post(f"/api/sales-funnels/{tunnel_id}/publish")
    assert "modifié" in client.post(f"/api/public/sales/{tunnel['slug']}/visit", json={}).json()["html"]
    versions = client.get(f"/api/sales-funnels/{tunnel_id}/pages/{page_id}/versions").json()
    assert len(versions) == 1
    restored = client.post(f"/api/sales-funnels/{tunnel_id}/pages/{page_id}/versions/{versions[0]['id']}/restore")
    assert restored.status_code == 200
    assert "modifié" not in restored.json()["pages"][0]["html"]
    assert "modifié" in client.post(f"/api/public/sales/{tunnel['slug']}/visit", json={}).json()["html"]


def test_guidance_rejects_missing_destination_and_unverified_action(client, monkeypatch):
    from app import sales

    monkeypatch.setattr(sales.settings, "openai_api_key", "test-key")
    assert client.post("/api/sales-funnels", json={**brief(), "goal_url": ""}).status_code == 422
    assert client.post("/api/sales-funnels", json={**brief(), "goal_url": "http://example.com"}).status_code == 422
    monkeypatch.setattr(sales, "revise_page", lambda *args, **kwargs: {"message": "", "region": None, "html": "<main><h1>Sans action</h1></main>"})
    assert client.post("/api/sales-funnels", json=brief()).status_code == 422
    monkeypatch.setattr(sales, "revise_page", lambda *args, **kwargs: {"message": "", "region": None, "html": "<main>data-sillage-next<form></form></main>"})
    assert client.post("/api/sales-funnels", json=brief()).status_code == 422


def test_sales_funnel_isolated_by_company(client):
    from app.database import SessionLocal
    from app.models import Company, User
    from app.security import hash_password

    tunnel = client.get("/api/sales-funnels").json()[0]
    with SessionLocal() as db:
        company = Company(name="Autre entreprise")
        db.add(company)
        db.flush()
        db.add(User(company_id=company.id, email="sales-other@example.org", full_name="Autre",
                    password_hash=hash_password("test-password")))
        db.commit()
    token = client.post("/api/auth/login", json={"email": "sales-other@example.org",
                                                  "password": "test-password"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/api/sales-funnels/{tunnel['id']}"
    assert client.get(path, headers=headers).status_code == 404
    assert client.get(f"{path}/stats", headers=headers).status_code == 404
    assert client.patch(f"{path}/destination", headers=headers,
                        json={"goal_url": "https://example.com"}).status_code == 404
    assert client.get("/api/sales-funnels", headers=headers).json() == []
    assert client.get("/api/sales-funnels/overview", headers=headers).json()["visits"] == 0


def published_funnel(client, monkeypatch):
    """Un tunnel publie, pour les gardes qui ont besoin d'un parcours vivant."""
    from app import sales

    monkeypatch.setattr(sales.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(sales, "revise_page", fake_page)
    created = client.post("/api/sales-funnels", json={**brief(), "name": "Garde du parcours"})
    assert created.status_code == 201, created.text
    tunnel = created.json()
    assert client.post(f"/api/sales-funnels/{tunnel['id']}/publish").status_code == 200
    return tunnel


def test_the_public_journey_is_capped(client, monkeypatch):
    """Les trois routes partagent un seul seau : fabriquer des sessions est gratuit.

    Le plafond est pose avant la resolution du tunnel, donc une rafale sur un
    slug inconnu compte aussi. Il est abaisse ici pour ne pas tirer cent vingt
    appels dans un test.
    """
    from app import sales

    monkeypatch.setattr(sales, "JOURNEY_CALLS", 3)
    for attempt in range(3):
        refused = client.post("/api/public/sales/slug-inconnu/visit", json={"source": "Email"})
        assert refused.status_code == 404, f"appel {attempt}"
    blocked = client.post("/api/public/sales/slug-inconnu/visit", json={"source": "Email"})
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    # Le seau est partage : /advance et /goal sont bloques aussi.
    assert client.post("/api/public/sales/slug-inconnu/advance").status_code == 429
    assert client.post("/api/public/sales/slug-inconnu/goal").status_code == 429


def test_a_journey_cookie_without_a_session_is_refused(client, monkeypatch):
    """Un jeton d'une forme anterieure doit donner 403, jamais 500.

    Sans identifiant de session, la deduplication des evenements ne tient plus :
    l'etape est inaccessible plutot que comptee deux fois.
    """
    import jwt

    from app import sales

    tunnel = published_funnel(client, monkeypatch)
    landing = next(page for page in tunnel["pages"] if page["role"] == "landing")
    token = jwt.encode({"tunnel": tunnel["id"], "page": landing["id"]},
                       sales.settings.secret_key, algorithm="HS256")
    client.cookies.set("sillage_sales_journey", token)
    try:
        assert client.post(f"/api/public/sales/{tunnel['slug']}/advance").status_code == 403
        assert client.post(f"/api/public/sales/{tunnel['slug']}/goal").status_code == 403
    finally:
        client.cookies.delete("sillage_sales_journey")


def test_old_events_are_forgotten(tmp_path):
    """La mesure de parcours a une duree de conservation."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import create_engine, select

    from app.database import Base, EVENT_RETENTION_DAYS, purge_old_events
    from app.models import TunnelEvent

    engine = create_engine(f"sqlite:///{tmp_path / 'mesure.db'}")
    Base.metadata.create_all(engine)
    maintenant = datetime.now(timezone.utc)
    with engine.begin() as connection:
        for suffixe, age in (("ancien", EVENT_RETENTION_DAYS + 5), ("recent", 3)):
            connection.execute(TunnelEvent.__table__.insert().values(
                id=suffixe, tunnel_id="t", page_id="p", session_id="s",
                event_key=f"s:p:{suffixe}", kind="page_view", source="Email",
                created_at=maintenant - timedelta(days=age)))
    with engine.begin() as connection:
        purge_old_events(connection)
    with engine.begin() as connection:
        restants = connection.execute(select(TunnelEvent.id)).scalars().all()
    engine.dispose()
    assert restants == ["recent"]
