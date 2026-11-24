import tempfile
import unittest
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from backend.main import create_app


APPLICATION = {
    "company": " Acme ",
    "position": "Engineering Intern",
    "location": "Remote",
    "dateApplied": "2026-11-23",
    "status": "Applied",
}


class APITests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.database = Path(directory) / "test.sqlite3"
        self.client = self.enterContext(TestClient(create_app(self.database)))

    def test_crud_and_persistence(self):
        self.assertEqual(self.client.get("/applications").json(), [])
        response = self.client.post("/applications", json=APPLICATION)
        self.assertEqual(response.status_code, 201, response.text)
        record = response.json()
        self.assertEqual(UUID(record["id"]).version, 4)
        self.assertEqual(record, {**APPLICATION, "company": "Acme", "id": record["id"]})
        with TestClient(create_app(self.database)) as restarted:
            self.assertEqual(restarted.get("/applications").json(), [record])

        url = f"/applications/{record['id']}"
        response = self.client.put(url, json={**APPLICATION, "status": "Interview"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {**record, "status": "Interview"})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(self.client.get("/applications").json(), [])
        self.assertEqual(self.client.put(url, json=APPLICATION).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_validation(self):
        for field, value in [
            ("company", "  "),
            ("status", "Pending"),
            ("dateApplied", "2026-02-30"),
            ("dateApplied", 0),
            ("dateApplied", "2026-11-23T00:00:00"),
            ("id", "caller-supplied"),
        ]:
            with self.subTest(field=field, value=value):
                response = self.client.post("/applications", json={**APPLICATION, field: value})
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.post("/applications", json={}).status_code, 422)
        self.assertEqual(self.client.get("/applications").json(), [])

    def test_statistics_and_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(self.client.get("/statistics").json(),
                         {"total": 0, "responses": 0, "interviews": 0, "offers": 0})
        for status in ("Applied", "Responded", "Interview", "Offer", "Rejected"):
            response = self.client.post("/applications", json={**APPLICATION, "status": status})
            self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.client.get("/statistics").json(),
                         {"total": 5, "responses": 4, "interviews": 1, "offers": 1})

    def test_import_is_atomic_and_safe_to_retry(self):
        first = {**APPLICATION, "id": "legacy-1"}
        second = {**APPLICATION, "id": "legacy-2", "status": "Offer"}
        url = "/applications/import"
        invalid = {**second, "status": "Unknown"}
        self.assertEqual(self.client.post(url, json={"applications": [first, invalid]}).status_code, 422)
        self.assertEqual(self.client.get("/applications").json(), [])

        existing = self.client.post("/applications", json=APPLICATION).json()
        collision = {**first, "id": existing["id"], "company": "Overwrite"}
        batch = {"applications": [first, second, first, collision]}
        response = self.client.post(url, json=batch)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"imported": 2, "skipped": 2})
        self.assertEqual(len(self.client.get("/applications").json()), 3)
        by_id = {row["id"]: row for row in self.client.get("/applications").json()}
        self.assertEqual(by_id[existing["id"]], existing)
        self.assertEqual(by_id[second["id"]], {**second, "company": "Acme"})

        self.assertEqual(self.client.delete("/applications/legacy-1").status_code, 204)
        self.assertEqual(self.client.post(url, json=batch).json(), {"imported": 0, "skipped": 4})
        self.assertEqual(len(self.client.get("/applications").json()), 2)

    def test_cors(self):
        for origin in (
            "http://localhost:5173", "http://localhost:5174",
            "http://127.0.0.1:5173", "http://127.0.0.1:5174",
        ):
            response = self.client.options("/applications", headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers["access-control-allow-origin"], origin)
        response = self.client.get("/applications", headers={"Origin": "https://example.org"})
        self.assertNotIn("access-control-allow-origin", response.headers)
