import os
from collections.abc import Iterator
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Request
from sqlalchemy import Connection, Engine, URL, create_engine, event
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import DeclarativeBase, Session

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")
SCHEMA_LOCK_ID = 711946270338792641


class Base(DeclarativeBase):
    pass


def parse_database_url(value: str | URL) -> URL:
    try:
        return make_url(value)
    except ArgumentError:
        raise ValueError("Invalid database URL. Check the server-side database configuration.") from None


def database_url() -> URL:
    configured = os.getenv("DATABASE_URL", "").strip()
    if configured:
        return parse_database_url(configured)
    # Keep honoring older local configurations when DATABASE_URL is unset.
    return URL.create("sqlite", database=os.getenv("DATABASE_PATH", "interntrack.sqlite3"))


def make_engine(target: Path | str | URL | None = None) -> Engine:
    if isinstance(target, Path):
        url = URL.create("sqlite", database=str(target.resolve()))
    else:
        url = parse_database_url(target) if target is not None else database_url()

    if url.drivername in {"postgres", "postgresql", "postgresql+psycopg"}:
        return create_engine(
            url.set(drivername="postgresql+psycopg"),
            connect_args={"connect_timeout": 5},
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_timeout=10,
            pool_recycle=1800,
            hide_parameters=True,
        )
    if url.drivername not in {"sqlite", "sqlite+pysqlite"}:
        raise ValueError("DATABASE_URL must use SQLite or PostgreSQL with psycopg.")

    if url.database and url.database != ":memory:" and url.query.get("uri") != "true":
        url = url.set(database=str(BACKEND_DIR / url.database))
    engine = create_engine(url, connect_args={"check_same_thread": False}, hide_parameters=True)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys = ON")

    return engine


def lock_schema(connection: Connection) -> None:
    """Serialize schema changes and legacy maintenance inside the caller's transaction."""
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    else:
        connection.exec_driver_sql(f"SELECT pg_advisory_xact_lock({SCHEMA_LOCK_ID})")


def conflict_insert(db: Session, model):
    insert = postgres_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    return insert(model)


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session
