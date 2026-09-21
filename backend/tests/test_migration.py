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
        "INSERT INTO campaigns VALUES ('camp2','c1','u1','Inscription portes ouvertes','inscription-evenement','Réservez votre place','information','draft','private',?,NULL,NULL,'{}',NULL,NULL,4,0,'2024-02-01 10:00:00','2024-03-01 10:00:00')",
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
            assert "fields" not in {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(campaigns)")}
            assert "campaign_id" not in {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(responses)")}

        # Une seconde ouverture ne doit rien rejouer.
        database.initialize_schema()
        with engine.begin() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM forms").scalar() == 2
    finally:
        engine.dispose()
        os.unlink(path)
