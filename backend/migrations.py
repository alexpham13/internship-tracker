from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine

from .database import BACKEND_DIR, lock_schema


def migration_config() -> Config:
    return Config(str(BACKEND_DIR.parent / "alembic.ini"))


def upgrade_schema(engine: Engine) -> None:
    config = migration_config()
    with engine.begin() as connection:
        lock_schema(connection)
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def require_current_schema(connection: Connection) -> None:
    current = set(MigrationContext.configure(connection).get_current_heads())
    expected = set(ScriptDirectory.from_config(migration_config()).get_heads())
    if current != expected:
        raise RuntimeError("Database schema is out of date. Run 'alembic upgrade head' before starting the API.")


def initialize_schema(engine: Engine) -> None:
    if engine.dialect.name == "sqlite":
        upgrade_schema(engine)
    else:
        with engine.connect() as connection:
            require_current_schema(connection)
