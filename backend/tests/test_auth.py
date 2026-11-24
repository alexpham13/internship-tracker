import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.auth import CSRF_HEADER, SESSION_SECONDS, digest
from backend.claim_legacy import assign_legacy
from backend.models import AuthRateLimit, AuthSession, User
from backend.tests.auth_support import app_for, HEADERS, ORIGIN, PASSWORD, client_for, register
from backend.tests.test_api import APPLICATION


class AuthTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = directory / "auth.sqlite3"
        self.app = app_for(self.path)
        self.client = self.enterContext(client_for(self.app))
        self.cookie = self.app.state.session_cookie

    def test_registration_hashes_password_and_issues_secure_session(self):
        response = register(self.client, "Owner@EXAMPLE.COM", " Test Owner ")
        account = response.json()
        self.assertEqual(account, {"id": account["id"], "name": "Test Owner", "legacy_access": False})
        attributes = response.headers["set-cookie"]
        for value in ("__Host-", "HttpOnly", "Secure", "Path=/", "SameSite=lax", f"Max-Age={SESSION_SECONDS}"):
            self.assertIn(value, attributes)
        self.assertNotIn("Domain=", attributes)
        token = self.client.cookies[self.cookie]
        with Session(self.app.state.engine) as db:
            user = db.get(User, account["id"])
            self.assertEqual(user.email, "owner@example.com")
            self.assertTrue(user.password_hash.startswith("$argon2id$"))
            self.assertNotIn(PASSWORD, user.password_hash)
            self.assertEqual(db.scalar(select(AuthSession.token_hash)), digest(token))
        self.assertEqual(self.client.get("/auth/me").json(), account)
        duplicate = self.client.post("/auth/register", json={
            "email": "owner@example.com", "name": "Other", "password": PASSWORD,
        })
        self.assertEqual(duplicate.status_code, 409)

    def test_login_rotates_cookie_and_logout_revokes_server_session(self):
        register(self.client)
        stale = self.client.cookies[self.cookie]
        known = self.client.post("/auth/login", json={"email": "owner@example.com", "password": "wrong"})
        unknown = self.client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
        self.assertEqual((known.status_code, known.json()), (401, unknown.json()))
        self.assertEqual(unknown.status_code, 401)
        response = self.client.post("/auth/login", json={"email": "OWNER@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        fresh = self.client.cookies[self.cookie]
        self.assertNotEqual(stale, fresh)
        with closing(client_for(self.app)) as replay:
            replay.cookies.set(self.cookie, stale)
            self.assertEqual(replay.get("/auth/me").status_code, 401)
        logout = self.client.post("/auth/logout")
        self.assertEqual(logout.status_code, 204)
        self.assertIn("Max-Age=0", logout.headers["set-cookie"])
        self.client.cookies.set(self.cookie, fresh)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)

    def test_expired_session_rejected_even_when_cookie_is_still_sent(self):
        register(self.client)
        with Session(self.app.state.engine) as db:
            db.execute(update(AuthSession).values(expires_at=int(time.time()) - 1))
            db.commit()
        self.assertIn(self.cookie, self.client.cookies)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/applications").status_code, 401)
        self.assertEqual(self.client.post("/applications", json=APPLICATION).status_code, 401)
        self.assertEqual(self.client.post("/auth/logout").status_code, 204)

    def test_authentication_covers_all_private_endpoints(self):
        fields = {"resume_text": "Synthetic resume", "job_description": "Synthetic posting"}
        for method, path, kwargs in (
            ("GET", "/applications", {}),
            ("GET", "/statistics", {}),
            ("POST", "/applications", {"json": APPLICATION}),
            ("PUT", "/applications/id", {"json": APPLICATION}),
            ("DELETE", "/applications/id", {}),
            ("POST", "/applications/import", {"json": {"applications": [{**APPLICATION, "id": "id"}]}}),
            ("POST", "/resume/extract", {"files": {"file": ("resume.pdf", b"resume", "application/pdf")}}),
            ("POST", "/resume/analyze", {"json": fields}),
            ("POST", "/cover-letter/generate", {"json": {**fields, "tone": "professional"}}),
        ):
            with self.subTest(path=path, method=method):
                self.assertEqual(self.client.request(method, path, **kwargs).status_code, 401)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_csrf_requires_an_explicit_allowed_origin_and_header(self):
        with closing(client_for(self.app, headers={})) as browser:
            body = {"name": "Test", "email": "owner@example.com", "password": PASSWORD}
            self.assertEqual(browser.post("/auth/register", json=body).status_code, 403)
            register(self.client)
            browser.cookies.update(self.client.cookies)
            for headers in ({}, {"Origin": ORIGIN}, {CSRF_HEADER: "1"},
                            {**HEADERS, "Origin": "https://evil.example"}):
                with self.subTest(headers=headers):
                    self.assertEqual(browser.post("/applications", json=APPLICATION, headers=headers).status_code, 403)
                    self.assertEqual(browser.post("/auth/logout", headers=headers).status_code, 403)
                    self.assertEqual(browser.post("/auth/login", json=body, headers=headers).status_code, 403)
            self.assertEqual(browser.get("/auth/me").status_code, 200)

    def test_input_validation_does_not_echo_passwords(self):
        for fields in (
            {"name": " ", "email": "owner@example.com", "password": PASSWORD},
            {"name": "Owner", "email": "not-an-email", "password": PASSWORD},
            {"name": "Owner", "email": "owner@example.com", "password": "short-private"},
            {"name": "Owner", "email": "owner@example.com", "password": PASSWORD, "legacy_access": True},
        ):
            with self.subTest(fields=list(fields)):
                response = self.client.post("/auth/register", json=fields)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn(fields["password"], response.text)

    def test_auth_rate_limits_account_across_ip_addresses_and_reset_after_window(self):
        body = {"email": "owner@example.com", "password": "wrong"}
        # All lookups share the same account limit even when the direct client changes.
        for address in ("192.0.2.10", "192.0.2.11"):
            with closing(client_for(self.app, address=address)) as browser:
                for _ in range(10):
                    self.assertEqual(browser.post("/auth/login", json=body).status_code, 401)
        response = self.client.post("/auth/login", json=body)
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers["retry-after"]), 0)
        with Session(self.app.state.engine) as db:
            db.execute(update(AuthRateLimit).values(expires_at=0))
            db.commit()
        self.assertEqual(self.client.post("/auth/login", json=body).status_code, 401)

    def test_account_isolation_including_statistics_and_import_ids(self):
        register(self.client)
        record = self.client.post("/applications", json=APPLICATION).json()
        path = "/applications/" + record["id"]
        shared_import = {"applications": [{**APPLICATION, "id": "legacy-browser-id", "status": "Offer"}]}
        self.assertEqual(self.client.post("/applications/import", json=shared_import).json()["imported"], 1)
        with closing(client_for(self.app)) as other:
            register(other, "other@example.com")
            self.assertEqual(other.get("/applications").json(), [])
            self.assertEqual(other.get("/statistics").json()["total"], 0)
            self.assertEqual(other.put(path, json=APPLICATION).status_code, 404)
            self.assertEqual(other.delete(path).status_code, 404)
            self.assertEqual(other.post("/applications/import", json=shared_import).json()["imported"], 1)
            self.assertEqual(other.delete("/applications/legacy-browser-id").status_code, 204)
        self.assertEqual(self.client.get("/statistics").json(), {
            "total": 2, "responses": 1, "interviews": 0, "offers": 1,
        })
        self.assertEqual(self.client.put(path, json=APPLICATION).json(), record)



class LegacyMigrationTests(unittest.TestCase):
    def test_legacy_records_and_tombstones_survive_restart_and_require_explicit_claim(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = directory / "legacy.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            db.executescript("""
                CREATE TABLE applications (
                    id VARCHAR(128) PRIMARY KEY, company VARCHAR NOT NULL, position VARCHAR NOT NULL,
                    location VARCHAR NOT NULL, date_applied DATE NOT NULL, status VARCHAR NOT NULL
                );
                CREATE TABLE imported_applications (id VARCHAR(128) PRIMARY KEY);
                INSERT INTO applications VALUES ('legacy-id', 'Legacy Co', 'Intern', 'Remote', '2026-01-01', 'Applied');
                INSERT INTO imported_applications VALUES ('legacy-deleted');
            """)
        app = app_for(path)
        with client_for(app) as intended:
            register(intended)
            self.assertEqual(intended.get("/applications").json(), [])
            self.assertEqual(intended.delete("/applications/legacy-id").status_code, 404)
            with closing(client_for(app)) as other:
                register(other, "other@example.com")
                assign_legacy(app.state.engine, "owner@example.com")
                self.assertEqual(other.get("/applications").json(), [])
                self.assertFalse(other.get("/auth/me").json()["legacy_access"])
                with self.assertRaises(ValueError):
                    assign_legacy(app.state.engine, "other@example.com")
            self.assertTrue(intended.get("/auth/me").json()["legacy_access"])
            self.assertEqual(intended.get("/applications").json()[0]["id"], "legacy-id")
            self.assertEqual(intended.post("/applications/import", json={
                "applications": [{**APPLICATION, "id": "legacy-deleted"}],
            }).json(), {"imported": 0, "skipped": 1})
            with client_for(app_for(path)) as restarted:
                restarted.cookies.update(intended.cookies)
                self.assertEqual(len(restarted.get("/applications").json()), 1)
