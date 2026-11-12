from logging.config import fileConfig

from alembic import context

from app import database, models  # noqa: F401  (models : enregistre toutes les tables)

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run_migrations(connection):
    # render_as_batch : les futurs ALTER passent aussi sur SQLite.
    context.configure(connection=connection, target_metadata=database.Base.metadata, render_as_batch=True)
    # Si la connexion est deja dans une transaction (demarrage de l'API), Alembic
    # n'ouvre ni ne valide rien : c'est l'appelant qui garde le verrou et valide.
    with context.begin_transaction():
        context.run_migrations()


# Connexion fournie par initialize_schema(), sinon (ligne de commande) celle de l'application.
connection = config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    with database.engine.connect() as connection:
        run_migrations(connection)
