import json

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

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

    if legacy:
        split_campaigns_into_forms(connection)


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
        connection.execute(text("INSERT INTO form_versions (id, form_id, snapshot, source, instruction, message, created_at) SELECT id, campaign_id, snapshot, source, instruction, message, created_at FROM campaign_versions"))
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
