import json

from sqlalchemy import MetaData, create_engine, func, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.schema import CreateIndex, CreateTable

from .config import settings


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
# Les accents restent lisibles dans le JSON stocke : la recherche plein texte de la
# boite de reception compare des caracteres, pas des sequences echappees.
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args, json_serializer=lambda value: json.dumps(value, ensure_ascii=False))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# Colonnes du formulaire, portees par `campaigns` avant la separation campagne / formulaire.
FORM_COLUMNS = ("name", "slug", "description", "kind", "status", "visibility", "fields", "design", "content", "thank_you", "draft", "brief", "visits", "archived", "created_at", "updated_at")

# Colonnes JSON ajoutees apres coup : d'anciennes lignes les portent encore a NULL,
# alors que le formulaire les veut toujours remplies.
JSON_DEFAULTS = {"fields": "[]", "design": "{}", "content": "{}", "thank_you": "{}", "brief": "{}"}

# La campagne ne garde que le dossier : le reste part dans `forms`.
DROPPED_CAMPAIGN_COLUMNS = ("slug", "description", "kind", "status", "visibility", "fields", "design", "content", "thank_you", "draft", "brief", "visits")


def initialize_schema():
    """Create and upgrade the MVP schema once, even with multiple API workers."""
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(736455141)"))
        elif engine.dialect.name == "sqlite":
            # Le pilote SQLite n'ouvre pas toujours une transaction avant le
            # premier DDL. Sans BEGIN explicite, un échec laisse une table
            # reconstruite à moitié et une reprise impossible.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        upgrade(connection)


def columns_of(connection, table: str) -> set[str]:
    inspector = inspect(connection)
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def add_column(connection, table: str, column: str, ddl: str):
    if column not in columns_of(connection, table):
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def upgrade(connection):
    # L'import charge les tables dans Base.metadata avant create_all, y compris
    # lorsque la migration est invoquee sans avoir importe l'API.
    from . import models  # noqa: F401

    campaign_columns = columns_of(connection, "campaigns")
    # Une base d'avant la separation : `campaigns` porte encore le formulaire.
    legacy = "fields" in campaign_columns
    if legacy:
        # Colonnes ajoutees apres coup : la reprise ci-dessous les lit toutes.
        for column in ("design", "content", "draft", "brief"):
            add_column(connection, "campaigns", column, "JSON")

    Base.metadata.create_all(bind=connection)

    add_column(connection, "companies", "logo", "TEXT DEFAULT ''")
    add_column(connection, "companies", "brand", "JSON")
    add_column(connection, "campaigns", "client", "VARCHAR(140) DEFAULT ''")
    add_column(connection, "campaigns", "objective", "TEXT DEFAULT ''")
    add_column(connection, "campaigns", "starts_on", "DATE")
    add_column(connection, "campaigns", "ends_on", "DATE")
    add_column(connection, "responses", "form_id", "VARCHAR(36)")
    add_column(connection, "form_versions", "screenshot_data_url", "TEXT")
    add_column(connection, "form_versions", "images", "JSON")
    add_column(connection, "forms", "identity", "JSON")
    add_column(connection, "tunnels", "kind", "VARCHAR(20) DEFAULT 'legacy_form'")
    add_column(connection, "tunnels", "brief", "JSON")
    add_column(connection, "tunnels", "identity", "JSON")
    add_column(connection, "tunnels", "goal_url", "VARCHAR(2048)")
    add_column(connection, "tunnels", "goal_label", "VARCHAR(100)")

    if legacy:
        split_campaigns_into_forms(connection)

    add_column(connection, "pages", "name", "VARCHAR(140)")
    add_column(connection, "pages", "settings", "JSON")
    connection.execute(text("UPDATE form_versions SET images = '[]' WHERE images IS NULL"))
    upgrade_pages_for_tunnels(connection)
    migrate_forms_to_pages(connection)
    migrate_forms_to_tunnels(connection)
    connection.execute(text(
        "UPDATE pages SET name = (SELECT forms.name FROM forms WHERE forms.id = pages.form_id) "
        "WHERE name IS NULL AND role = 'form' AND form_id IS NOT NULL"
    ))
    connection.execute(text("UPDATE pages SET name = 'Page de remerciement' WHERE name IS NULL AND role = 'thanks'"))
    connection.execute(text("UPDATE pages SET name = 'Page de présentation' WHERE name IS NULL AND role = 'landing'"))
    connection.execute(text("UPDATE pages SET name = 'Étape' WHERE name IS NULL"))
    connection.execute(text(
        "UPDATE pages SET settings = (SELECT forms.thank_you FROM forms WHERE forms.id = pages.form_id) "
        "WHERE settings IS NULL AND role = 'thanks' AND form_id IS NOT NULL"
    ))
    connection.execute(text("UPDATE pages SET settings = '{}' WHERE settings IS NULL"))
    connection.execute(text(
        "UPDATE forms SET thank_you = '{}' WHERE id IN "
        "(SELECT form_id FROM pages WHERE role = 'thanks' AND form_id IS NOT NULL)"
    ))
    freeze_form_identity(connection)


def freeze_form_identity(connection):
    """Fige sur chaque formulaire l'identite de marque qu'il applique deja.

    L'identite etait relue sur le compte a chaque retouche : changer ses
    couleurs faisait silencieusement deriver toutes les pages existantes a leur
    modification suivante. Chaque formulaire garde desormais la sienne. La
    reprise copie l'etat courant, donc rien ne bouge a l'oeil.
    """
    rows = connection.execute(text(
        "SELECT forms.id, companies.name, companies.sector, companies.tone, "
        "companies.primary_color, companies.accent_color, companies.brand "
        "FROM forms JOIN campaigns ON campaigns.id = forms.campaign_id "
        "JOIN companies ON companies.id = campaigns.company_id "
        "WHERE forms.identity IS NULL"
    )).all()
    for form_id, name, sector, tone, primary, accent, brand in rows:
        if isinstance(brand, str):
            brand = json.loads(brand or "{}")
        identity = {"name": name, "sector": sector, "tone": tone,
                    "primary_color": primary, "accent_color": accent, "brand": brand or {}}
        connection.execute(
            text("UPDATE forms SET identity = :identity WHERE id = :id"),
            {"identity": json.dumps({key: value for key, value in identity.items() if value}, ensure_ascii=False), "id": form_id},
        )


def upgrade_pages_for_tunnels(connection):
    """Rend les pages autonomes tout en gardant les documents du Lot 1."""
    from .models import Form, Page, Tunnel

    page_columns = {column["name"]: column for column in inspect(connection).get_columns("pages")}
    if connection.dialect.name == "sqlite" and not page_columns["form_id"]["nullable"]:
        # SQLite ne sait pas retirer NOT NULL. La nouvelle table est remplie et
        # verifiee avant de remplacer l'ancienne dans la transaction courante.
        metadata = MetaData()
        Form.__table__.to_metadata(metadata)
        Tunnel.__table__.to_metadata(metadata)
        replacement = Page.__table__.to_metadata(metadata, name="pages_lot3_new")
        connection.execute(CreateTable(replacement))
        existing_columns = [column.name for column in Page.__table__.columns if column.name in page_columns]
        names = ", ".join(existing_columns)
        connection.execute(text(f"INSERT INTO pages_lot3_new ({names}) SELECT {names} FROM pages"))
        old_count = connection.scalar(text("SELECT count(*) FROM pages"))
        new_count = connection.scalar(text("SELECT count(*) FROM pages_lot3_new"))
        if old_count != new_count:
            raise RuntimeError("La copie des pages est incomplete")
        connection.execute(text("PRAGMA defer_foreign_keys = ON"))
        connection.execute(text("DROP TABLE pages"))
        connection.execute(text("ALTER TABLE pages_lot3_new RENAME TO pages"))
        for index in Page.__table__.indexes:
            connection.execute(CreateIndex(index))
    else:
        if connection.dialect.name == "postgresql" and not page_columns["form_id"]["nullable"]:
            connection.execute(text("ALTER TABLE pages ALTER COLUMN form_id DROP NOT NULL"))
        add_column(connection, "pages", "tunnel_id", "VARCHAR(36) REFERENCES tunnels(id)")
        add_column(connection, "pages", "next_page_url", "VARCHAR(2048)")
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_pages_tunnel_id ON pages (tunnel_id)"))


def migrate_forms_to_tunnels(connection):
    """Un tunnel initial stable par formulaire existant, sans toucher aux réponses."""
    from .models import Form, Page, Tunnel, initial_tunnel_id

    forms = Form.__table__
    pages = Page.__table__
    tunnels = Tunnel.__table__
    existing_tunnels = set(connection.execute(select(tunnels.c.id)).scalars())
    entry_pages = {
        row.form_id: row
        for row in connection.execute(select(pages.c.id, pages.c.form_id, pages.c.tunnel_id).where(pages.c.role == "form"))
        if row.form_id is not None
    }

    for form in connection.execute(select(forms)):
        entry = entry_pages.get(form.id)
        if entry is None:
            continue
        tunnel_id = entry.tunnel_id or initial_tunnel_id(form.id)
        if tunnel_id not in existing_tunnels:
            connection.execute(tunnels.insert().values(
                id=tunnel_id, campaign_id=form.campaign_id, name=form.name,
                slug=form.slug, status=form.status, entry_page_id=entry.id,
                created_at=form.created_at, updated_at=form.updated_at,
            ))
            existing_tunnels.add(tunnel_id)
        connection.execute(
            pages.update()
            .where(pages.c.form_id == form.id, pages.c.tunnel_id.is_(None))
            .values(tunnel_id=tunnel_id)
        )


def migrate_forms_to_pages(connection):
    """Ajoute les documents manquants sans reecrire les donnees existantes."""
    from .models import Campaign, Company, Form, FormResponse, Page, thanks_page_id
    from .page_document import legacy_to_html, prepare_page

    forms = Form.__table__
    campaigns = Campaign.__table__
    companies = Company.__table__
    pages = Page.__table__
    responses = FormResponse.__table__
    company_by_id = {
        row._mapping["id"]: dict(row._mapping)
        for row in connection.execute(select(companies))
    }
    campaign_company_ids = {
        campaign_id: company_id
        for campaign_id, company_id in connection.execute(
            select(campaigns.c.id, campaigns.c.company_id)
        )
    }
    existing = {
        (row.form_id, row.role): row.id
        for row in connection.execute(select(pages.c.id, pages.c.form_id, pages.c.role))
    }
    response_counts = {
        form_id: count
        for form_id, count in connection.execute(
            select(responses.c.form_id, func.count(responses.c.id)).group_by(responses.c.form_id)
        )
    }

    for row in connection.execute(select(forms)):
        form = dict(row._mapping)
        form_id = form["id"]
        missing_form = (form_id, "form") not in existing
        missing_thanks = (form_id, "thanks") not in existing
        if not missing_form and not missing_thanks:
            continue

        company = company_by_id[campaign_company_ids[form["campaign_id"]]]

        state = {
            "name": form["name"], "description": form["description"],
            "kind": form["kind"], "fields": form["fields"] or [],
            "design": form["design"] or {}, "content": form["content"] or {},
            "thank_you": form["thank_you"] or {},
        }
        draft = form["draft"] or None
        thanks_id = existing.get((form_id, "thanks")) or thanks_page_id(form_id)
        response_count = response_counts.get(form_id, 0)

        if missing_thanks:
            thanks_html, thanks_manifest = prepare_page(
                legacy_to_html(state, company, role="thanks"), require_form=False
            )
            draft_thanks_html = None
            draft_thanks_manifest = None
            if draft and draft.get("thank_you") != state["thank_you"]:
                draft_thanks_html, draft_thanks_manifest = prepare_page(
                    legacy_to_html({**state, **draft}, company, role="thanks"), require_form=False
                )
            connection.execute(pages.insert().values(
                id=thanks_id, form_id=form_id, name="Page de remerciement", slug=None, role="thanks", position=1,
                next_page_id=None, html=thanks_html, draft_html=draft_thanks_html,
                manifest=thanks_manifest, draft_manifest=draft_thanks_manifest, settings=form["thank_you"] or {},
                visits=response_count, conversions=0,
                created_at=form["created_at"], updated_at=form["updated_at"],
            ))

        if missing_form:
            html, manifest = prepare_page(legacy_to_html(state, company), require_form=True)
            draft_html = None
            draft_manifest = None
            if draft:
                draft_html, draft_manifest = prepare_page(
                    legacy_to_html({**state, **draft}, company), require_form=True
                )
            connection.execute(pages.insert().values(
                id=form_id, form_id=form_id, name=form["name"], slug=form["slug"], role="form", position=0,
                next_page_id=thanks_id, html=html, draft_html=draft_html,
                manifest=manifest, draft_manifest=draft_manifest, settings={},
                visits=form["visits"] or 0, conversions=response_count,
                created_at=form["created_at"], updated_at=form["updated_at"],
            ))


def split_campaigns_into_forms(connection):
    """Reprise unique : chaque campagne devient un dossier plus un formulaire.

    Le formulaire reprend l'identifiant et le slug de la campagne : les liens deja
    diffuses, les reponses collectees et les exports restent valides.
    """
    columns = ", ".join(FORM_COLUMNS)
    empty = "::json" if connection.dialect.name == "postgresql" else ""
    values = ", ".join(f"coalesce({name}, '{JSON_DEFAULTS[name]}'{empty})" if name in JSON_DEFAULTS else name for name in FORM_COLUMNS)
    connection.execute(text(f"INSERT INTO forms (id, campaign_id, creator_id, {columns}) SELECT id, id, creator_id, {values} FROM campaigns"))
    connection.execute(text("UPDATE responses SET form_id = campaign_id"))
    if inspect(connection).has_table("campaign_versions"):
        connection.execute(text("INSERT INTO form_versions (id, form_id, snapshot, source, instruction, message, created_at, images) SELECT id, campaign_id, snapshot, source, instruction, message, created_at, '[]' FROM campaign_versions"))
        connection.execute(text("DROP TABLE campaign_versions"))

    # SQLite refuse de supprimer une colonne indexee : l'index part d'abord.
    connection.execute(text("DROP INDEX IF EXISTS ix_campaigns_slug"))
    connection.execute(text("DROP INDEX IF EXISTS ix_responses_campaign_id"))
    for column in DROPPED_CAMPAIGN_COLUMNS:
        connection.execute(text(f"ALTER TABLE campaigns DROP COLUMN {column}"))
    connection.execute(text("ALTER TABLE responses DROP COLUMN campaign_id"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
