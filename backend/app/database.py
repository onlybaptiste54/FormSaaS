from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def initialize_schema():
    """Create and upgrade the MVP schema once, even with multiple API workers."""
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(736455141)"))
            Base.metadata.create_all(bind=connection)
            for column in ("design", "content", "draft"):
                connection.execute(text(f"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS {column} JSON"))
        return
    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("campaigns")}
    for column in ("design", "content", "draft"):
        if column not in columns:
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE campaigns ADD COLUMN {column} JSON"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
