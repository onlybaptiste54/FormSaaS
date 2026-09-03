from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def ensure_compatible_schema():
    """Keep existing MVP databases compatible until formal migrations are introduced."""
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS design JSON"))
        return
    columns = {column["name"] for column in inspect(engine).get_columns("campaigns")}
    if "design" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE campaigns ADD COLUMN design JSON"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
