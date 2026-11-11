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
    action = "data-sillage-goal" if role == "offer" else "data-sillage-next"
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
    assert client.get(f"/api/public/sales/{slug}/document").status_code == 404

    published = client.post(f"/api/sales-funnels/{tunnel['id']}/publish")
    assert published.status_code == 200

    # Le document est la page elle-meme, pas une enveloppe autour d'elle.
    first = client.get(f"/api/public/sales/{slug}/document", params={"source": "Email"})
    assert first.status_code == 200, first.text
    assert first.headers["content-type"].startswith("text/html")
    assert first.text.startswith("<!doctype html>")
    assert "<h1>landing</h1>" in first.text
    assert "<title>" in first.text and tunnel["name"] in first.text
    # Le bouton reste un bouton : le CSS de Luna continue de s'appliquer.
    offre = tunnel["pages"][1]["slug"]
    assert f'<form action="/t/{slug}/{offre}" method="get" style="display:contents">' in first.text
    assert "<button" in first.text and 'type="submit"' in first.text

    client.get(f"/api/public/sales/{slug}/document", params={"source": "Réseaux sociaux"})
    second = client.get(f"/api/public/sales/{slug}/document", params={"step": offre})
    assert second.status_code == 200
    assert "<h1>offer</h1>" in second.text
    # Derniere etape : plus de passage, seulement l'action finale.
    assert f'/t/{slug}/go' in second.text
    assert 'method="get"' not in second.text or f'/t/{slug}/go' in second.text

    goal = client.get(f"/api/public/sales/{slug}/go", follow_redirects=False)
    assert goal.status_code == 303
    assert goal.headers["location"] == brief()["goal_url"]
    assert client.get(f"/api/public/sales/{slug}/go", follow_redirects=False).status_code == 303
    stats = client.get(f"/api/sales-funnels/{tunnel['id']}/stats").json()
    assert stats["visits"] == 1
    assert stats["goals"] == 1
    assert stats["conversion"] == 100.0
    assert stats["sources"] == [{"source": "Email", "visits": 1, "goals": 1}]
    assert [page["visits"] for page in stats["pages"]] == [1, 1]
    # Arriver sur l'etape suivante vaut clic sur le bouton de la precedente.
    assert stats["pages"][0]["actions"] == 1
    assert stats["daily"][-1]["visits"] == 1
    overview = client.get("/api/sales-funnels/overview").json()
    assert overview["active"] >= 1
    assert overview["visits"] == 1
    assert overview["goals"] == 1
    updated = client.patch(f"/api/sales-funnels/{tunnel['id']}/destination",
                           json={"goal_url": "https://example.com/nouveau"})
    assert updated.status_code == 200
    assert client.get(f"/api/public/sales/{slug}/go", follow_redirects=False).headers["location"] == "https://example.com/nouveau"
    assert client.patch(f"/api/sales-funnels/{tunnel['id']}/destination",
                        json={"goal_url": "http://example.com"}).status_code == 422
    exported = client.get(f"/api/sales-funnels/{tunnel['id']}/export.zip")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert set(archive.namelist()) == {"index.html", f"{offre}.html", "LISEZ-MOI.txt"}
        assert f"{offre}.html" in archive.read("index.html").decode()
        assert "https://example.com/nouveau" in archive.read(f"{offre}.html").decode()


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
    assert "modifié" not in client.get(f"/api/public/sales/{tunnel['slug']}/document").text
    client.post(f"/api/sales-funnels/{tunnel_id}/publish")
    assert "modifié" in client.get(f"/api/public/sales/{tunnel['slug']}/document").text
    versions = client.get(f"/api/sales-funnels/{tunnel_id}/pages/{page_id}/versions").json()
    assert len(versions) == 1
    restored = client.post(f"/api/sales-funnels/{tunnel_id}/pages/{page_id}/versions/{versions[0]['id']}/restore")
    assert restored.status_code == 200
    assert "modifié" not in restored.json()["pages"][0]["html"]
    assert "modifié" in client.get(f"/api/public/sales/{tunnel['slug']}/document").text


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
        refused = client.get("/api/public/sales/slug-inconnu/document")
        assert refused.status_code == 404, f"appel {attempt}"
    blocked = client.get("/api/public/sales/slug-inconnu/document")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    # Le seau est partage : l'action finale est bloquee aussi.
    assert client.get("/api/public/sales/slug-inconnu/go").status_code == 429


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
        assert client.get(f"/api/public/sales/{tunnel['slug']}/go").status_code == 403
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


def test_a_funnel_grows_beyond_two_steps(client, monkeypatch):
    """Ajouter, déplacer, supprimer : la chaîne et les positions restent d'accord."""
    tunnel = published_funnel(client, monkeypatch)
    added = client.post(f"/api/sales-funnels/{tunnel['id']}/pages",
                        json={"name": "Preuves", "instruction": "Montre les résultats obtenus par des clients."})
    assert added.status_code == 201, added.text
    pages = added.json()["tunnel"]["pages"]
    assert [page["name"] for page in pages] == ["Découverte", "Preuves", "L'offre"]
    assert [page["position"] for page in pages] == [0, 1, 2]
    # La chaîne suit l'ordre, et la dernière étape ne mène nulle part.
    assert [page["next_page_id"] for page in pages] == [pages[1]["id"], pages[2]["id"], None]
    assert added.json()["tunnel"]["entry_page_id"] == pages[0]["id"]
    assert added.json()["warnings"] == []

    # Déplacer l'offre en tête laisse deux boutons mal placés : on le dit.
    moved = client.patch(f"/api/sales-funnels/{tunnel['id']}/pages/{pages[2]['id']}", json={"position": 0})
    assert moved.status_code == 200, moved.text
    assert [page["name"] for page in moved.json()["tunnel"]["pages"]] == ["L'offre", "Découverte", "Preuves"]
    warnings = " ".join(moved.json()["warnings"])
    assert "L'offre" in warnings and "Preuves" in warnings

    # Et on revient en arrière.
    back = client.patch(f"/api/sales-funnels/{tunnel['id']}/pages/{pages[2]['id']}", json={"position": 2})
    assert back.json()["warnings"] == []

    removed = client.delete(f"/api/sales-funnels/{tunnel['id']}/pages/{pages[1]['id']}")
    assert removed.status_code == 200, removed.text
    remaining = removed.json()["tunnel"]["pages"]
    assert [page["name"] for page in remaining] == ["Découverte", "L'offre"]
    assert [page["next_page_id"] for page in remaining] == [remaining[1]["id"], None]
    # Un tunnel garde deux étapes.
    assert client.delete(f"/api/sales-funnels/{tunnel['id']}/pages/{remaining[0]['id']}").status_code == 422


def test_an_added_step_must_lead_somewhere(client, monkeypatch):
    """Une étape intermédiaire sans bouton de passage est refusée."""
    from app import sales

    tunnel = published_funnel(client, monkeypatch)

    def cul_de_sac(html, instruction, identity, **kwargs):
        return {"message": "Page prête", "region": None,
                "html": "<!doctype html><html><head><style>body{color:#111}</style></head>"
                        "<body><main><h1>Preuves</h1></main></body></html>"}

    monkeypatch.setattr(sales, "revise_page", cul_de_sac)
    refused = client.post(f"/api/sales-funnels/{tunnel['id']}/pages",
                          json={"name": "Preuves", "instruction": "Montre les résultats obtenus."})
    assert refused.status_code == 422
    assert "passage" in refused.json()["detail"]


def test_the_final_action_works_from_any_step(client, monkeypatch):
    """Un visiteur convaincu dès la première étape doit pouvoir partir."""
    tunnel = published_funnel(client, monkeypatch)
    slug = tunnel["slug"]
    assert client.get(f"/api/public/sales/{slug}/document", params={"source": "Email"}).status_code == 200
    goal = client.get(f"/api/public/sales/{slug}/go", follow_redirects=False)
    assert goal.status_code == 303, goal.text
    assert goal.headers["location"] == "https://example.com/reserver"
    client.cookies.delete("sillage_sales_journey")


def test_the_export_follows_the_real_chain(client, monkeypatch):
    """Trois étapes, trois fichiers, et chacun saute vers le suivant."""
    import io
    import zipfile

    tunnel = published_funnel(client, monkeypatch)
    assert client.post(f"/api/sales-funnels/{tunnel['id']}/pages",
                       json={"name": "Preuves", "instruction": "Montre les résultats obtenus."}).status_code == 201
    etapes = [page["slug"] for page in client.get(f"/api/sales-funnels/{tunnel['id']}").json()["pages"]]
    exported = client.get(f"/api/sales-funnels/{tunnel['id']}/export.zip")
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        # Un fichier par étape, nommé comme son adresse publique.
        assert set(archive.namelist()) == {"index.html", f"{etapes[1]}.html", f"{etapes[2]}.html", "LISEZ-MOI.txt"}
        assert f"{etapes[1]}.html" in archive.read("index.html").decode()
        assert f"{etapes[2]}.html" in archive.read(f"{etapes[1]}.html").decode()
        # La dernière ne saute que vers l'adresse externe.
        derniere = archive.read(f"{etapes[2]}.html").decode()
        assert "https://example.com/reserver" in derniere
        assert ".html" not in derniere.split("<script>")[1]
        assert "Preuves" in archive.read("LISEZ-MOI.txt").decode()


def test_a_published_funnel_carries_a_reference(client, monkeypatch):
    """Titre et description, repli compris, et sans rien compter."""
    tunnel = published_funnel(client, monkeypatch)
    slug = tunnel["slug"]

    # Par défaut : le nom du tunnel et son offre.
    assert tunnel["seo"]["custom"] is False
    assert tunnel["seo"]["title"] == tunnel["name"]
    assert tunnel["seo"]["description"].startswith("Un accompagnement de six semaines")

    meta = client.get(f"/api/public/sales/{slug}/meta")
    assert meta.status_code == 200, meta.text
    assert meta.json()["title"] == tunnel["name"]
    assert "<h1" in meta.json()["html"]

    # Lire la référence n'est pas une visite.
    before = client.get(f"/api/sales-funnels/{tunnel['id']}").json()["pages"][0]["visits"]
    client.get(f"/api/public/sales/{slug}/meta")
    assert client.get(f"/api/sales-funnels/{tunnel['id']}").json()["pages"][0]["visits"] == before

    saved = client.patch(f"/api/sales-funnels/{tunnel['id']}/seo",
                         json={"title": "Structurer sa prospection", "description": "Six semaines pour trouver des clients réguliers."})
    assert saved.status_code == 200, saved.text
    assert saved.json()["seo"] == {"title": "Structurer sa prospection",
                                   "description": "Six semaines pour trouver des clients réguliers.",
                                   "custom": True}
    assert client.get(f"/api/public/sales/{slug}/meta").json()["title"] == "Structurer sa prospection"

    # Vider les deux champs ramène le repli.
    cleared = client.patch(f"/api/sales-funnels/{tunnel['id']}/seo", json={"title": "", "description": ""})
    assert cleared.json()["seo"]["custom"] is False


def test_only_published_funnels_are_referenced(client, monkeypatch):
    """Un brouillon n'a ni référence publique ni place dans le sitemap."""
    from app import sales

    monkeypatch.setattr(sales.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(sales, "revise_page", fake_page)
    draft = client.post("/api/sales-funnels", json={**brief(), "name": "Brouillon non publie"}).json()

    assert client.get(f"/api/public/sales/{draft['slug']}/meta").status_code == 404
    listed = client.get("/api/public/sales-sitemap")
    assert listed.status_code == 200
    slugs = [item["slug"] for item in listed.json()]
    assert draft["slug"] not in slugs

    assert client.post(f"/api/sales-funnels/{draft['id']}/publish").status_code == 200
    assert draft["slug"] in [item["slug"] for item in client.get("/api/public/sales-sitemap").json()]
    assert client.post(f"/api/sales-funnels/{draft['id']}/pause").status_code == 200
    assert draft["slug"] not in [item["slug"] for item in client.get("/api/public/sales-sitemap").json()]


def test_each_step_gets_a_readable_and_distinct_address(client, monkeypatch):
    """Deux étapes du même nom ne peuvent pas partager une adresse."""
    tunnel = published_funnel(client, monkeypatch)
    premier = client.post(f"/api/sales-funnels/{tunnel['id']}/pages",
                          json={"name": "Preuves", "instruction": "Montre les résultats obtenus."})
    assert premier.status_code == 201
    second = client.post(f"/api/sales-funnels/{tunnel['id']}/pages",
                         json={"name": "Preuves", "instruction": "Montre d'autres résultats."})
    assert second.status_code == 201
    adresses = [page["slug"] for page in second.json()["tunnel"]["pages"]]
    assert len(set(adresses)) == len(adresses)
    assert any(slug.startswith("preuves") for slug in adresses)


def test_a_step_can_never_take_the_final_action_address(client, monkeypatch):
    """« go » mène à l'action finale : une étape ainsi nommée prend autre chose."""
    tunnel = published_funnel(client, monkeypatch)
    ajout = client.post(f"/api/sales-funnels/{tunnel['id']}/pages",
                        json={"name": "Go", "instruction": "Invite à poursuivre la lecture."})
    assert ajout.status_code == 201
    assert "go" not in [page["slug"] for page in ajout.json()["tunnel"]["pages"]]


def test_an_unknown_step_address_is_not_found(client, monkeypatch):
    """Une adresse d'étape inventée ne sert aucune page."""
    tunnel = published_funnel(client, monkeypatch)
    assert client.get(f"/api/public/sales/{tunnel['slug']}/document",
                      params={"step": "etape-inventee"}).status_code == 404


def test_existing_sales_steps_are_given_an_address(tmp_path):
    """La reprise nomme les étapes des tunnels déjà en base, sans collision."""
    from sqlalchemy import create_engine, text

    from app.database import Base, name_sales_steps

    engine = create_engine(f"sqlite:///{tmp_path / 'ancien.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO tunnels (id, campaign_id, name, slug, status, kind, brief, identity, created_at, updated_at) "
            "VALUES ('t1', 'c1', 'Tunnel', 'tunnel', 'active', 'sales', '{}', '{}', '2026-01-01', '2026-01-01')"))
        for numero, nom in ((1, "Découverte"), (2, "Découverte"), (3, "Go")):
            connection.execute(text(
                "INSERT INTO pages (id, tunnel_id, name, role, position, html, manifest, visits, conversions, "
                "created_at, updated_at) VALUES (:id, 't1', :nom, 'step', :pos, '<p>x</p>', '[]', 0, 0, "
                "'2026-01-01', '2026-01-01')"),
                {"id": f"p{numero}", "nom": nom, "pos": numero})
    with engine.begin() as connection:
        name_sales_steps(connection)
    with engine.begin() as connection:
        adresses = [slug for (slug,) in connection.execute(
            text("SELECT slug FROM pages ORDER BY position")).all()]
    engine.dispose()
    assert adresses[0] == "decouverte"
    assert adresses[1] == "decouverte-2"
    assert adresses[2] != "go"


def variante_de(client, tunnel_id, page_id, nom=""):
    reponse = client.post(f"/api/sales-funnels/{tunnel_id}/pages/{page_id}/variants",
                          json={"name": nom})
    assert reponse.status_code == 201, reponse.text
    page = next(item for item in reponse.json()["pages"] if item["id"] == page_id)
    return page["variants"][-1]


def test_a_variant_starts_as_a_copy_and_is_edited_on_its_own(client, monkeypatch):
    """On compare deux rédactions du même propos, pas une page contre rien."""
    from app import sales

    tunnel = published_funnel(client, monkeypatch)
    entree = tunnel["pages"][0]
    variante = variante_de(client, tunnel["id"], entree["id"])
    assert variante["name"] == "Version B"
    assert "<h1>landing</h1>" in variante["html"]

    # La retouche vise la version, pas l'étape.
    monkeypatch.setattr(sales.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(sales, "revise_page", fake_page)
    retouche = client.post(f"/api/sales-funnels/{tunnel['id']}/pages/{entree['id']}/refine",
                           json={"instruction": "Rends le titre plus direct.", "variant_id": variante["id"]})
    assert retouche.status_code == 200, retouche.text
    apres = next(item for item in retouche.json()["tunnel"]["pages"] if item["id"] == entree["id"])
    assert "modifié" in apres["variants"][0]["html"]
    # L'étape témoin n'a pas bougé.
    assert "modifié" not in apres["html"]


def test_a_session_always_sees_the_same_version(client, monkeypatch):
    """Voir A puis B ne mesurerait rien : le tirage est figé dans le cookie."""
    tunnel = published_funnel(client, monkeypatch)
    entree = tunnel["pages"][0]
    variante_de(client, tunnel["id"], entree["id"])
    assert client.post(f"/api/sales-funnels/{tunnel['id']}/publish").status_code == 200

    slug = tunnel["slug"]
    client.cookies.delete("sillage_sales_journey")
    premier = client.get(f"/api/public/sales/{slug}/document").text
    for _ in range(6):
        assert client.get(f"/api/public/sales/{slug}/document").text == premier
    client.cookies.delete("sillage_sales_journey")


def test_both_versions_are_served_across_sessions(client, monkeypatch):
    """Sur plusieurs sessions, les deux versions sortent."""
    from app import sales

    tunnel = published_funnel(client, monkeypatch)
    entree = tunnel["pages"][0]
    variante = variante_de(client, tunnel["id"], entree["id"])
    assert client.post(f"/api/sales-funnels/{tunnel['id']}/publish").status_code == 200

    tirages = iter(["", variante["id"], "", variante["id"]])
    def tirage(options):
        voulu = next(tirages)
        return voulu if voulu in options else options[0]
    monkeypatch.setattr(sales.random, "choice", tirage)
    for _ in range(4):
        client.cookies.delete("sillage_sales_journey")
        assert client.get(f"/api/public/sales/{tunnel['slug']}/document").status_code == 200
    client.cookies.delete("sillage_sales_journey")

    chiffres = client.get(f"/api/sales-funnels/{tunnel['id']}/stats").json()
    versions = next(page for page in chiffres["pages"] if page["id"] == entree["id"])["variants"]
    assert [item["name"] for item in versions] == ["Version A (témoin)", "Version B"]
    assert [item["visits"] for item in versions] == [2, 2]


def test_the_final_click_is_credited_to_the_version_seen(client, monkeypatch):
    """Le clic final arrive plus loin : il remonte à la version vue à l'entrée."""
    from app import sales

    tunnel = published_funnel(client, monkeypatch)
    entree, offre = tunnel["pages"][0], tunnel["pages"][1]
    variante = variante_de(client, tunnel["id"], entree["id"])
    assert client.post(f"/api/sales-funnels/{tunnel['id']}/publish").status_code == 200
    slug = tunnel["slug"]

    for choisi in (variante["id"], ""):
        monkeypatch.setattr(sales.random, "choice",
                            lambda options, valeur=choisi: valeur if valeur in options else options[0])
        client.cookies.delete("sillage_sales_journey")
        assert client.get(f"/api/public/sales/{slug}/document").status_code == 200
        assert client.get(f"/api/public/sales/{slug}/document", params={"step": offre["slug"]}).status_code == 200
        if choisi:
            assert client.get(f"/api/public/sales/{slug}/go", follow_redirects=False).status_code == 303
    client.cookies.delete("sillage_sales_journey")

    versions = next(page for page in client.get(f"/api/sales-funnels/{tunnel['id']}/stats").json()["pages"]
                    if page["id"] == entree["id"])["variants"]
    temoin = next(item for item in versions if item["id"] == "")
    comparee = next(item for item in versions if item["id"] == variante["id"])
    assert comparee["goals"] == 1 and comparee["conversion"] == 100.0
    assert temoin["goals"] == 0 and temoin["conversion"] == 0.0


def test_promoting_a_version_ends_the_comparison(client, monkeypatch):
    """La version retenue devient l'étape, et on peut revenir en arrière."""
    from app import sales

    tunnel = published_funnel(client, monkeypatch)
    entree = tunnel["pages"][0]
    variante = variante_de(client, tunnel["id"], entree["id"])
    monkeypatch.setattr(sales.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(sales, "revise_page", fake_page)
    client.post(f"/api/sales-funnels/{tunnel['id']}/pages/{entree['id']}/refine",
                json={"instruction": "Rends le titre plus direct.", "variant_id": variante["id"]})
    assert client.post(f"/api/sales-funnels/{tunnel['id']}/publish").status_code == 200

    promue = client.post(f"/api/sales-funnels/{tunnel['id']}/pages/{entree['id']}/variants/{variante['id']}/promote")
    assert promue.status_code == 200, promue.text
    apres = next(item for item in promue.json()["tunnel"]["pages"] if item["id"] == entree["id"])
    assert "modifié" in apres["html"]
    assert apres["variants"] == []
    # Le document precedent reste restaurable.
    versions = client.get(f"/api/sales-funnels/{tunnel['id']}/pages/{entree['id']}/versions").json()
    assert len(versions) >= 1
