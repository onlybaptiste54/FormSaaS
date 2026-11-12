import os
import tempfile

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


@pytest.fixture
def sqlite_engine(monkeypatch):
    from app import database

    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.unlink(path)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(database, "engine", engine)
    yield engine
    engine.dispose()
    if os.path.exists(path):
        os.unlink(path)


def head_revision():
    from app import database

    with database.engine.connect() as connection:
        return ScriptDirectory.from_config(database.alembic_config(connection)).get_current_head()


def current_revision(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()


def test_empty_database_gets_every_table_and_no_drift(sqlite_engine):
    from app import database, models

    database.initialize_schema()

    assert current_revision(sqlite_engine) == [head_revision()]
    with sqlite_engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        assert {table.name for table in models.Base.metadata.sorted_tables} <= tables
        # Echoue si un modele change sans revision Alembic : `alembic revision --autogenerate`.
        assert compare_metadata(MigrationContext.configure(connection), models.Base.metadata) == []


def test_legacy_path_only_knows_tables_that_exist():
    from app import database, models

    # La reprise historique ne cree que ces tables ; toute table ajoutee ensuite
    # vient d'une revision, pas de `create_all`.
    assert {table.name for table in models.Base.metadata.sorted_tables} >= set(database.BASELINE_TABLES)


def test_database_without_alembic_version_is_upgraded_then_stamped(sqlite_engine):
    from app import database, models

    # Une base d'avant Alembic ne porte que les tables du schema de base.
    models.Base.metadata.create_all(sqlite_engine, tables=[
        table for table in models.Base.metadata.sorted_tables if table.name in database.BASELINE_TABLES
    ])
    with sqlite_engine.begin() as connection:
        connection.execute(models.Company.__table__.insert().values(id="c1", name="Atelier", dpo_email="dpo@example.fr"))

    database.initialize_schema()

    assert current_revision(sqlite_engine) == [head_revision()]
    with sqlite_engine.connect() as connection:
        assert connection.execute(text("SELECT name FROM companies WHERE id = 'c1'")).scalar() == "Atelier"


def test_second_start_changes_nothing(sqlite_engine):
    from app import database

    database.initialize_schema()
    first = current_revision(sqlite_engine)
    database.initialize_schema()

    assert current_revision(sqlite_engine) == first == [head_revision()]


def test_failed_start_leaves_no_half_applied_schema(sqlite_engine, monkeypatch):
    from alembic import command

    from app import database

    def boom(*args, **kwargs):
        raise RuntimeError("echec simule")

    monkeypatch.setattr(command, "upgrade", boom)
    with pytest.raises(RuntimeError):
        database.initialize_schema()

    with sqlite_engine.connect() as connection:
        assert inspect(connection).get_table_names() == []
