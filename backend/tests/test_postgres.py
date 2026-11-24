import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from backend.auth import take_attempt
from backend.claim_legacy import assign_legacy
from backend.database import make_engine
from backend.migrations import initialize_schema, upgrade_schema
from backend.models import Application, AuthRateLimit, AuthSession, ImportedApplication, User
from backend.tests import test_api, test_auth
from backend.tests.auth_support import PASSWORD, app_for, client_for, register
from backend.transfer_database import transfer_sqlite

TEST_URL = os.getenv("TEST_POSTGRES_URL", "").strip()


class PostgresFixture:
    def make_test_schema(self):
        admin = make_engine(TEST_URL)
        self.addCleanup(admin.dispose)
        self.assertEqual(admin.dialect.name, "postgresql", "TEST_POSTGRES_URL must point to PostgreSQL.")
        schema = f"interntrack_test_{uuid4().hex}"
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))

        def drop_test_schema():
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))

        self.addCleanup(drop_test_schema)
        options = admin.url.query.get("options", "")
        return admin.url.update_query_dict({"options": f"{options} -csearch_path={schema}".strip()})

    def setUp(self):
        self.database = self.make_test_schema()
        self.engine = make_engine(self.database)
        self.addCleanup(self.engine.dispose)
        upgrade_schema(self.engine)
        self.app = app_for(self.database)
        self.client = self.enterContext(client_for(self.app))
        self.cookie = self.app.state.session_cookie


@unittest.skipUnless(TEST_URL, "Set TEST_POSTGRES_URL to run against real PostgreSQL.")
class PostgreSQLApplicationTests(PostgresFixture, test_api.APITests):
    def setUp(self):
        super().setUp()
        register(self.client)


@unittest.skipUnless(TEST_URL, "Set TEST_POSTGRES_URL to run against real PostgreSQL.")
class PostgreSQLAuthTests(PostgresFixture, test_auth.AuthTests):
    pass


@unittest.skipUnless(TEST_URL, "Set TEST_POSTGRES_URL to run against real PostgreSQL.")
class PostgreSQLMigrationTests(PostgresFixture, unittest.TestCase):
    def test_requires_explicit_upgrade_and_retains_pool_settings(self):
        engine = make_engine(self.make_test_schema())
        self.addCleanup(engine.dispose)
        with self.assertRaisesRegex(RuntimeError, "alembic upgrade head"):
            initialize_schema(engine)
        upgrade_schema(engine)
        upgrade_schema(engine)
        initialize_schema(engine)
        self.assertEqual(engine.dialect.driver, "psycopg")
        self.assertEqual(engine.pool.size(), 5)
        self.assertEqual(engine.pool.timeout(), 10)

    def test_concurrent_updates_enforce_rate_limit(self):
        def attempt(_index):
            with Session(self.engine) as db:
                try:
                    take_attempt(db, "synthetic-concurrent-key", 3)
                except HTTPException as error:
                    return error.status_code
                return 200

        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(attempt, range(8)))
        self.assertEqual(sorted(results), [200] * 3 + [429] * 5)

    def test_transfer_preserves_durable_data_and_rejects_repeat(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source_path = directory / "backup with spaces.sqlite3"
        record = {**test_api.APPLICATION, "id": "same-id", "status": "Offer"}
        batch = {"applications": [record]}
        with client_for(app_for(source_path)) as source:
            owner = register(source).json()
            self.assertEqual(source.post("/applications/import", json=batch).json()["imported"], 1)
            tombstone = {"applications": [{**record, "id": "deleted-id"}]}
            self.assertEqual(source.post("/applications/import", json=tombstone).status_code, 200)
            self.assertEqual(source.delete("/applications/deleted-id").status_code, 204)
        source_engine = make_engine(source_path)
        self.addCleanup(source_engine.dispose)
        with source_engine.begin() as connection:
            connection.execute(Application.__table__.insert().values(
                id="unassigned", company="Legacy", position="Intern", location="Remote",
                date_applied=date(2026, 1, 1), status="Applied",
            ))
        before = source_path.read_bytes()

        self.assertEqual(transfer_sqlite(source_path, self.engine), {
            "users": 1, "applications": 2, "imported_applications": 2,
        })
        self.assertEqual(source_path.read_bytes(), before)
        for model in (AuthSession, AuthRateLimit):
            with self.engine.connect() as connection:
                self.assertEqual(connection.scalar(select(func.count()).select_from(model)), 0)
        with self.assertRaisesRegex(ValueError, "already contains"):
            transfer_sqlite(source_path, self.engine)

        login = self.client.post("/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json(), owner)
        self.assertEqual([item["id"] for item in self.client.get("/applications").json()], ["same-id"])
        self.assertEqual(self.client.post("/applications/import", json=tombstone).json()["skipped"], 1)
        assign_legacy(self.engine, "owner@example.com")
        self.assertTrue(self.client.get("/auth/me").json()["legacy_access"])
        self.assertEqual({item["id"] for item in self.client.get("/applications").json()}, {"same-id", "unassigned"})
        self.assertEqual(self.client.post("/applications", json=test_api.APPLICATION).status_code, 201)
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(select(func.count()).select_from(User)), 1)
            self.assertEqual(connection.scalar(select(func.count()).select_from(ImportedApplication)), 2)

    def test_failed_transfer_rolls_back_rows_copied_before_the_error(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source_path = directory / "invalid-backup.sqlite3"
        with client_for(app_for(source_path)) as source:
            register(source)
        # Simulate an old SQLite writer that disabled foreign keys.
        with closing(sqlite3.connect(source_path)) as connection, connection:
            connection.execute("""
                INSERT INTO applications (user_id, id, company, position, location, date_applied, status)
                VALUES ('missing-user', 'orphan', 'Example Co', 'Intern', 'Remote', '2026-01-01', 'Applied')
            """)
        with self.assertRaises(IntegrityError):
            transfer_sqlite(source_path, self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(select(func.count()).select_from(User)), 0)
            self.assertEqual(connection.scalar(select(func.count()).select_from(Application)), 0)
