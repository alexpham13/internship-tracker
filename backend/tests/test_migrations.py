import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect, select

from backend.auth import digest
from backend.database import Base, make_engine
from backend.migrations import upgrade_schema
from backend.models import AuthRateLimit, AuthSession, User
from backend.tests.auth_support import app_for, client_for


class SQLiteMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = directory / "migration.sqlite3"
        self.engine = make_engine(self.path)
        self.addCleanup(self.engine.dispose)

    def test_prefers_database_url_and_keeps_legacy_sqlite_fallback(self):
        with patch.dict("os.environ", {
            "DATABASE_URL": "sqlite:///preferred.sqlite3", "DATABASE_PATH": "fallback.sqlite3",
        }):
            engine = make_engine()
            self.addCleanup(engine.dispose)
            self.assertEqual(Path(engine.url.database).name, "preferred.sqlite3")
        with patch.dict("os.environ", {"DATABASE_URL": "", "DATABASE_PATH": str(self.path)}):
            engine = make_engine()
            self.addCleanup(engine.dispose)
            self.assertEqual(Path(engine.url.database), self.path)

    def test_adopts_unversioned_auth_schema_without_replacing_users_or_sessions(self):
        Base.metadata.create_all(self.engine)
        token = "a" * 43
        expires_at = int(time.time()) + 3600
        with self.engine.begin() as connection:
            connection.execute(User.__table__.insert().values(
                id="user", email="existing@example.com", name="Existing User", password_hash="existing-hash",
            ))
            connection.execute(AuthSession.__table__.insert().values(
                token_hash=digest(token), user_id="user", expires_at=expires_at,
            ))
            connection.execute(AuthRateLimit.__table__.insert().values(
                key="existing-rate-limit", expires_at=expires_at, attempts=3,
            ))
        app = app_for(self.path)
        with client_for(app) as client:
            client.cookies.set(app.state.session_cookie, token)
            self.assertEqual(client.get("/auth/me").json()["name"], "Existing User")
        upgrade_schema(self.engine)
        with self.engine.connect() as connection:
            self.assertIn("alembic_version", inspect(connection).get_table_names())
            self.assertEqual(connection.scalars(select(User.password_hash)).all(), ["existing-hash"])
            self.assertEqual(connection.scalars(select(AuthSession.expires_at)).all(), [expires_at])
            self.assertEqual(connection.scalars(select(AuthRateLimit.attempts)).all(), [3])

    def test_unrecognized_schema_rolls_back_data_and_schema_changes(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript("""
                CREATE TABLE applications (
                    id VARCHAR(128) PRIMARY KEY, company VARCHAR NOT NULL, position VARCHAR NOT NULL,
                    location VARCHAR NOT NULL, date_applied DATE NOT NULL, status VARCHAR NOT NULL
                );
                INSERT INTO applications VALUES ('keep', 'Legacy Co', 'Intern', 'Remote', '2026-01-01', 'Applied');
                CREATE TABLE imported_applications (unexpected VARCHAR);
            """)
        with self.assertRaisesRegex(RuntimeError, "Unrecognized SQLite table layout"):
            upgrade_schema(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(inspect(connection).get_table_names(), ["applications", "imported_applications"])
            self.assertEqual(connection.exec_driver_sql("SELECT id FROM applications").scalars().all(), ["keep"])
