from alembic import context

from backend.database import Base, lock_schema, make_engine
from backend.models import Application, AuthRateLimit, AuthSession, ImportedApplication, User  # noqa: F401


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, transactional_ddl=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Run migrations online so Alembic can inspect and safely adopt existing SQLite tables.")

existing_connection = context.config.attributes.get("connection")
if existing_connection is not None:
    migrate(existing_connection)
else:
    engine = make_engine()
    try:
        with engine.begin() as connection:
            lock_schema(connection)
            migrate(connection)
    finally:
        engine.dispose()
