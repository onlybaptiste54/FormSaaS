import os
import sqlite3
import tempfile


# Schema d'avant la separation campagne / formulaire, tel qu'il existe en production.
LEGACY_SCHEMA = """
CREATE TABLE companies (id VARCHAR(36) NOT NULL PRIMARY KEY, name VARCHAR(120), legal_name VARCHAR(160), sector VARCHAR(80), siret VARCHAR(20), address VARCHAR(240), primary_color VARCHAR(7), accent_color VARCHAR(7), tone VARCHAR(40), dpo_email VARCHAR(160), logo TEXT, brand JSON, created_at DATETIME);
CREATE TABLE users (id VARCHAR(36) NOT NULL PRIMARY KEY, company_id VARCHAR(36) REFERENCES companies(id), email VARCHAR(160), full_name VARCHAR(120), password_hash VARCHAR(256), role VARCHAR(30), created_at DATETIME);
CREATE TABLE campaigns (id VARCHAR(36) NOT NULL PRIMARY KEY, company_id VARCHAR(36) REFERENCES companies(id), creator_id VARCHAR(36) REFERENCES users(id), name VARCHAR(140), slug VARCHAR(160), description TEXT, kind VARCHAR(30), status VARCHAR(20), visibility VARCHAR(30), fields JSON, design JSON, content JSON, thank_you JSON, draft JSON, brief JSON, visits INTEGER, archived BOOLEAN, created_at DATETIME, updated_at DATETIME);
CREATE UNIQUE INDEX ix_campaigns_slug ON campaigns (slug);
CREATE INDEX ix_campaigns_company_id ON campaigns (company_id);
CREATE TABLE campaign_versions (id VARCHAR(36) NOT NULL PRIMARY KEY, campaign_id VARCHAR(36) REFERENCES campaigns(id), snapshot JSON, source VARCHAR(20), instruction TEXT, message TEXT, created_at DATETIME);
CREATE INDEX ix_campaign_versions_campaign_id ON campaign_versions (campaign_id);
CREATE TABLE responses (id VARCHAR(36) NOT NULL PRIMARY KEY, campaign_id VARCHAR(36) NOT NULL, answers JSON, source VARCHAR(40), promo_code VARCHAR(60), consent BOOLEAN, consent_text TEXT, ip_address VARCHAR(64), user_agent VARCHAR(300), created_at DATETIME);
CREATE INDEX ix_responses_campaign_id ON responses (campaign_id);
CREATE TABLE templates (id VARCHAR(36) NOT NULL PRIMARY KEY, company_id VARCHAR(36) REFERENCES companies(id), source_key VARCHAR(80), name VARCHAR(140), description TEXT, category VARCHAR(40), fields JSON, design JSON, thank_you JSON, uses INTEGER, created_at DATETIME, updated_at DATETIME);
"""

FIELDS = '[{"id": "name", "label": "Nom", "type": "text", "required": true}, {"id": "consent", "label": "J\'accepte", "type": "consent", "required": true}]'


def legacy_database(path: str):
    connection = sqlite3.connect(path)
    connection.executescript(LEGACY_SCHEMA)
    connection.execute("INSERT INTO companies VALUES ('c1','Atelier Rivage','Atelier Rivage SAS','Services','','','#2F6B4F','#EE755C','Professionnel','dpo@rivage.fr','','{}','2024-01-01 10:00:00')")
    connection.execute("INSERT INTO users VALUES ('u1','c1','demo@sillage.fr','Camille','x','admin','2024-01-01 10:00:00')")
    connection.execute(
        "INSERT INTO campaigns VALUES ('camp1','c1','u1','Contact site principal','contact-site-principal','Parlons de votre projet','contact','active','private',?,'{}','{}','{\"title\": \"Merci\", \"message\": \"Bien reçu\"}',NULL,'{}',120,0,'2024-02-01 10:00:00','2024-03-01 10:00:00')",
        (FIELDS,),
    )
    # Ligne d'avant l'ajout de design, content et brief : ces colonnes sont restees vides.
    connection.execute(
        "INSERT INTO campaigns VALUES ('camp2','c1','u1','Inscription portes ouvertes','inscription-evenement','Réservez votre place','information','draft','private',?,NULL,NULL,'{}','{\"name\": \"Titre en préparation\"}',NULL,4,0,'2024-02-01 10:00:00','2024-03-01 10:00:00')",
        (FIELDS,),
    )
    connection.execute("INSERT INTO campaign_versions VALUES ('v1','camp1','{\"name\": \"Contact site principal\"}','publish','','Modifications publiées','2024-03-01 10:00:00')")
    connection.execute("INSERT INTO responses VALUES ('r1','camp1','{\"name\": \"Léa Bernard\"}','QR Code','',1,'J''accepte','192.0.2.1','demo','2024-03-02 10:00:00')")
    connection.commit()
    connection.close()


def test_existing_links_responses_and_history_survive_the_migration(monkeypatch):
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.unlink(path)
    legacy_database(path)

    from sqlalchemy import create_engine

    # Les tables ne sont connues de `Base.metadata` qu'une fois les modeles importes.
    from app import database, models  # noqa: F401

    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(database, "engine", engine)
    try:
        database.initialize_schema()

        with engine.begin() as connection:
            forms = connection.exec_driver_sql("SELECT id, campaign_id, name, slug, status, visits FROM forms ORDER BY id").fetchall()
            assert forms == [
                ("camp1", "camp1", "Contact site principal", "contact-site-principal", "active", 120),
                ("camp2", "camp2", "Inscription portes ouvertes", "inscription-evenement", "draft", 4),
            ]
            # Les colonnes JSON vides d'une ancienne ligne sont remplies, pas recopiees a NULL.
            assert connection.exec_driver_sql("SELECT design, content, brief FROM forms WHERE id = 'camp2'").fetchall() == [("{}", "{}", "{}")]
            # La campagne devient le dossier, nommee comme son formulaire.
            assert connection.exec_driver_sql("SELECT name FROM campaigns ORDER BY id").scalars().all() == ["Contact site principal", "Inscription portes ouvertes"]
            assert connection.exec_driver_sql("SELECT form_id FROM responses").scalar() == "camp1"
            assert connection.exec_driver_sql("SELECT form_id, source FROM form_versions").fetchall() == [("camp1", "publish")]
            assert connection.exec_driver_sql("SELECT screenshot_data_url, images FROM form_versions WHERE id = 'v1'").one() == (None, "[]")
            tunnels = connection.exec_driver_sql(
                "SELECT id, campaign_id, name, slug, status, entry_page_id FROM tunnels ORDER BY campaign_id"
            ).fetchall()
            assert len(tunnels) == 2
            assert tunnels[0].campaign_id == "camp1" and tunnels[0].slug == "contact-site-principal"
            assert tunnels[0].entry_page_id == "camp1"
            assert tunnels[1].campaign_id == "camp2" and tunnels[1].slug == "inscription-evenement"
            assert tunnels[1].entry_page_id == "camp2"
            pages = connection.exec_driver_sql(
                "SELECT id, form_id, slug, role, position, next_page_id, visits, conversions "
                "FROM pages ORDER BY form_id, position"
            ).fetchall()
            assert len(pages) == 4
            assert pages[0].id == "camp1" and pages[0].slug == "contact-site-principal"
            assert pages[0].role == "form" and pages[0].visits == 120 and pages[0].conversions == 1
            assert pages[1].role == "thanks" and pages[0].next_page_id == pages[1].id
            assert pages[1].visits == 1
            assert pages[2].id == "camp2" and pages[2].slug == "inscription-evenement"
            assert pages[2].visits == 4 and pages[2].conversions == 0
            assert pages[3].role == "thanks" and pages[2].next_page_id == pages[3].id
            assert connection.exec_driver_sql(
                "SELECT DISTINCT tunnel_id FROM pages WHERE form_id = 'camp1'"
            ).scalars().all() == [tunnels[0].id]
            assert connection.exec_driver_sql(
                "SELECT DISTINCT tunnel_id FROM pages WHERE form_id = 'camp2'"
            ).scalars().all() == [tunnels[1].id]
            assert all(connection.exec_driver_sql("SELECT html FROM pages WHERE id = ?", (page.id,)).scalar() for page in pages)
            draft_html = connection.exec_driver_sql("SELECT draft_html FROM pages WHERE id = 'camp2'").scalar()
            assert draft_html and "Titre en préparation" in draft_html
            assert connection.exec_driver_sql("SELECT draft_manifest FROM pages WHERE id = 'camp2'").scalar()
            assert "fields" not in {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(campaigns)")}
            assert "campaign_id" not in {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(responses)")}

        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE pages SET html = '<!doctype html><title>Retouche</title>' WHERE id = 'camp1'")
            connection.exec_driver_sql("UPDATE tunnels SET name = 'Tunnel retouché' WHERE campaign_id = 'camp1'")

        # Une seconde ouverture ne doit rien rejouer.
        database.initialize_schema()
        with engine.begin() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM forms").scalar() == 2
            assert connection.exec_driver_sql("SELECT count(*) FROM pages").scalar() == 4
            assert connection.exec_driver_sql("SELECT count(*) FROM tunnels").scalar() == 2
            assert connection.exec_driver_sql("SELECT name FROM tunnels WHERE campaign_id = 'camp1'").scalar() == "Tunnel retouché"
            assert connection.exec_driver_sql("SELECT html FROM pages WHERE id = 'camp1'").scalar() == "<!doctype html><title>Retouche</title>"
            assert connection.exec_driver_sql("SELECT answers FROM responses WHERE id = 'r1'").scalar() == '{"name": "Léa Bernard"}'
            assert connection.exec_driver_sql("SELECT snapshot FROM form_versions WHERE id = 'v1'").scalar() == '{"name": "Contact site principal"}'
            assert connection.exec_driver_sql("SELECT images FROM form_versions WHERE id = 'v1'").scalar() == "[]"
    finally:
        engine.dispose()
        os.unlink(path)


def test_existing_form_rows_gain_pages_without_changing_their_data(monkeypatch):
    """La production actuelle a deja la table forms, mais pas encore pages."""
    from datetime import datetime, timezone

    from sqlalchemy import create_engine

    from app import database, models

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.unlink(path)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(database, "engine", engine)
    try:
        models.Base.metadata.create_all(engine, tables=[
            table for table in models.Base.metadata.sorted_tables if table.name not in {"pages", "form_versions"}
        ])
        now = datetime(2024, 5, 1, tzinfo=timezone.utc)
        with engine.begin() as connection:
            # Version du schéma avant les captures persistées.
            connection.exec_driver_sql("CREATE TABLE form_versions (id VARCHAR(36) PRIMARY KEY, form_id VARCHAR(36), snapshot JSON, source VARCHAR(20), instruction TEXT, message TEXT, created_at DATETIME)")
            connection.execute(models.Company.__table__.insert().values(id="c1", name="Atelier", dpo_email="dpo@example.fr"))
            connection.execute(models.User.__table__.insert().values(id="u1", company_id="c1", email="a@example.fr", full_name="A", password_hash="x"))
            connection.execute(models.Campaign.__table__.insert().values(id="c1", company_id="c1", creator_id="u1", name="Campagne"))
            connection.execute(models.Form.__table__.insert().values(
                id="f1", campaign_id="c1", creator_id="u1", name="Contact", slug="contact",
                fields=[{"id": "email", "label": "Email", "type": "email", "required": True},
                        {"id": "consent", "label": "J'accepte", "type": "consent", "required": True}],
                draft={"name": "Contact retouché"}, visits=12, created_at=now,
            ))
            connection.execute(models.FormResponse.__table__.insert().values(
                id="r1", form_id="f1", answers={"email": "a@example.fr"}, consent=True,
            ))
            connection.exec_driver_sql("INSERT INTO form_versions (id, form_id, snapshot, source) VALUES ('v1', 'f1', '{\"name\": \"Contact\"}', 'manual')")

        database.initialize_schema()
        with engine.begin() as connection:
            pages = connection.execute(models.Page.__table__.select().order_by(models.Page.position)).mappings().all()
            assert len(pages) == 2
            assert pages[0]["id"] == "f1" and pages[0]["slug"] == "contact"
            assert pages[0]["draft_html"] and pages[0]["draft_manifest"]
            assert pages[0]["visits"] == 12 and pages[0]["conversions"] == 1
            assert pages[0]["next_page_id"] == pages[1]["id"]
            assert pages[1]["role"] == "thanks" and pages[1]["visits"] == 1
            tunnel = connection.execute(models.Tunnel.__table__.select()).mappings().one()
            assert tunnel["campaign_id"] == "c1" and tunnel["slug"] == "contact"
            assert tunnel["entry_page_id"] == "f1"
            assert all(page["tunnel_id"] == tunnel["id"] for page in pages)
            assert connection.execute(models.FormResponse.__table__.select()).mappings().one()["answers"] == {"email": "a@example.fr"}
            assert connection.execute(models.FormVersion.__table__.select()).mappings().one()["snapshot"] == {"name": "Contact"}
            assert connection.execute(models.FormVersion.__table__.select()).mappings().one()["images"] == []
            assert connection.exec_driver_sql("SELECT screenshot_data_url FROM form_versions WHERE id = 'v1'").scalar() is None

        database.initialize_schema()
        with engine.begin() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM form_versions").scalar() == 1
            assert connection.exec_driver_sql("SELECT images FROM form_versions WHERE id = 'v1'").scalar() == "[]"
            assert connection.exec_driver_sql("SELECT count(*) FROM tunnels").scalar() == 1
    finally:
        engine.dispose()
        os.unlink(path)


def test_fresh_seed_creates_pages_for_each_demo_form(monkeypatch):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app import database, models
    from app.seed import seed

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.unlink(path)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(database, "engine", engine)
    try:
        database.initialize_schema()
        with Session(engine) as db:
            seed(db)
        database.initialize_schema()
        with Session(engine) as db:
            forms = db.scalars(select(models.Form)).all()
            pages = db.scalars(select(models.Page)).all()
            tunnels = db.scalars(select(models.Tunnel)).all()
            assert len(forms) == 3 and len(pages) == 6
            assert len(tunnels) == 3
            for form in forms:
                form_page, thanks_page = sorted(form.pages, key=lambda page: page.position)
                tunnel = next(item for item in tunnels if item.entry_page_id == form_page.id)
                assert tunnel.campaign_id == form.campaign_id
                assert tunnel.slug == form.slug
                assert form_page.tunnel_id == tunnel.id == thanks_page.tunnel_id
                assert form_page.slug == form.slug
                assert form_page.next_page_id == thanks_page.id
                assert form_page.conversions == len(form.responses)
                assert thanks_page.visits == len(form.responses)
    finally:
        engine.dispose()
        os.unlink(path)


def test_lot1_pages_become_tunnel_pages_without_losing_data(monkeypatch):
    """La colonne form_id du Lot 1 était obligatoire et doit devenir facultative."""
    from sqlalchemy import create_engine, event

    from app import database, models

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.unlink(path)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    monkeypatch.setattr(database, "engine", engine)
    try:
        tables = [table for table in models.Base.metadata.sorted_tables if table.name not in {"pages", "tunnels"}]
        models.Base.metadata.create_all(engine, tables=tables)
        with engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE pages (
                    id VARCHAR(36) NOT NULL PRIMARY KEY, form_id VARCHAR(36) NOT NULL,
                    slug VARCHAR(160) UNIQUE, role VARCHAR(20) NOT NULL, position INTEGER NOT NULL,
                    next_page_id VARCHAR(36), html TEXT NOT NULL, draft_html TEXT,
                    manifest JSON NOT NULL, draft_manifest JSON, visits INTEGER NOT NULL,
                    conversions INTEGER NOT NULL, created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL, CONSTRAINT uq_pages_form_role UNIQUE (form_id, role),
                    FOREIGN KEY(form_id) REFERENCES forms(id), FOREIGN KEY(next_page_id) REFERENCES pages(id)
                )
            """)
            connection.exec_driver_sql("CREATE INDEX ix_pages_form_id ON pages (form_id)")
            connection.execute(models.Company.__table__.insert().values(id="c1", name="Atelier"))
            connection.execute(models.User.__table__.insert().values(
                id="u1", company_id="c1", email="a@example.fr", full_name="A", password_hash="x"
            ))
            connection.execute(models.Campaign.__table__.insert().values(
                id="c1", company_id="c1", creator_id="u1", name="Campagne"
            ))
            connection.execute(models.Form.__table__.insert().values(
                id="f1", campaign_id="c1", creator_id="u1", name="Contact", slug="contact",
                fields=[{"id": "email", "label": "Email", "type": "email"}], visits=27,
            ))
            connection.execute(models.FormResponse.__table__.insert().values(
                id="r1", form_id="f1", answers={"email": "client@example.fr"}, consent=True,
            ))
            connection.execute(models.FormVersion.__table__.insert().values(
                id="v1", form_id="f1", snapshot={"html": "ancienne version"}, source="manual",
            ))
            connection.exec_driver_sql("""
                INSERT INTO pages (id, form_id, slug, role, position, next_page_id, html, manifest,
                                   visits, conversions, created_at, updated_at)
                VALUES ('thank1', 'f1', NULL, 'thanks', 1, NULL, '<h1>Merci</h1>', '[]',
                        6, 0, '2024-01-01', '2024-01-01')
            """)
            connection.exec_driver_sql("""
                INSERT INTO pages (id, form_id, slug, role, position, next_page_id, html, manifest,
                                   visits, conversions, created_at, updated_at)
                VALUES ('f1', 'f1', 'contact', 'form', 0, 'thank1', '<form>Original</form>', '[]',
                        27, 6, '2024-01-01', '2024-01-01')
            """)

        database.initialize_schema()
        with engine.begin() as connection:
            assert next(column for column in connection.exec_driver_sql("PRAGMA table_info(pages)")
                        if column[1] == "form_id")[3] == 0
            assert connection.exec_driver_sql(
                "SELECT id, slug, next_page_id, html, visits, conversions FROM pages WHERE id = 'f1'"
            ).one() == ("f1", "contact", "thank1", "<form>Original</form>", 27, 6)
            tunnel = connection.execute(models.Tunnel.__table__.select()).mappings().one()
            assert tunnel["entry_page_id"] == "f1"
            assert connection.exec_driver_sql("SELECT count(*) FROM pages WHERE tunnel_id = ?", (tunnel["id"],)).scalar() == 2
            assert connection.execute(models.FormResponse.__table__.select()).mappings().one()["answers"] == {"email": "client@example.fr"}
            assert connection.execute(models.FormVersion.__table__.select()).mappings().one()["snapshot"] == {"html": "ancienne version"}
            for page_id, position in (("step1", 2), ("step2", 3)):
                connection.execute(models.Page.__table__.insert().values(
                    id=page_id, form_id=None, tunnel_id=tunnel["id"], role="step",
                    position=position, html="<p>Étape</p>", manifest=[],
                ))
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []

        database.initialize_schema()
        with engine.begin() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM tunnels").scalar() == 1
            assert connection.exec_driver_sql("SELECT count(*) FROM pages").scalar() == 4
            assert connection.exec_driver_sql("SELECT count(*) FROM pages WHERE role = 'step'").scalar() == 2
    finally:
        engine.dispose()
        os.unlink(path)


def test_failed_sqlite_upgrade_rolls_back_page_rebuild(monkeypatch):
    from pytest import raises
    from sqlalchemy import create_engine, inspect

    from app import database, models

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.unlink(path)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(database, "engine", engine)
    try:
        models.Base.metadata.create_all(engine, tables=[
            table for table in models.Base.metadata.sorted_tables if table.name not in {"pages", "tunnels"}
        ])
        with engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE pages (
                    id VARCHAR(36) PRIMARY KEY, form_id VARCHAR(36) NOT NULL,
                    role VARCHAR(20) NOT NULL, position INTEGER NOT NULL,
                    html TEXT NOT NULL, manifest JSON NOT NULL,
                    visits INTEGER NOT NULL, conversions INTEGER NOT NULL,
                    created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
                )
            """)

        def fail_after_rebuild(_connection):
            raise RuntimeError("Échec simulé après reconstruction")

        monkeypatch.setattr(database, "migrate_forms_to_tunnels", fail_after_rebuild)
        with raises(RuntimeError, match="Échec simulé"):
            database.initialize_schema()

        with engine.connect() as connection:
            assert not inspect(connection).has_table("tunnels")
            assert not inspect(connection).has_table("pages_lot3_new")
            columns = {column["name"]: column for column in inspect(connection).get_columns("pages")}
            assert columns["form_id"]["nullable"] is False
            assert "tunnel_id" not in columns
    finally:
        engine.dispose()
        os.unlink(path)
