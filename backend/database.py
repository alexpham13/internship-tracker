import os
from collections.abc import Iterator
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Request
from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")


class Base(DeclarativeBase):
    pass


def database_path() -> Path:
    return BACKEND_DIR / os.getenv("DATABASE_PATH", "interntrack.sqlite3")


def make_engine(path: Path):
    engine = create_engine(
        URL.create("sqlite", database=str(path)),
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys = ON")

    return engine


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session
