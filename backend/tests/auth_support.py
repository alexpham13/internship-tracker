from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import URL

from backend.auth import CSRF_HEADER, DEFAULT_ORIGINS
from backend.main import create_app

ORIGIN = "http://localhost:5173"
HEADERS = {"Origin": ORIGIN, CSRF_HEADER: "1"}
PASSWORD = "synthetic password for tests"


def app_for(path: Path | URL, *, secure: bool = True, origins=DEFAULT_ORIGINS) -> FastAPI:
    with patch.dict("os.environ", {
        "AUTH_COOKIE_SECURE": str(secure).lower(),
        "AUTH_ALLOWED_ORIGINS": ",".join(origins),
    }):
        return create_app(path)


def client_for(app: FastAPI, *, headers=HEADERS, address="testclient", base_url="https://testserver") -> TestClient:
    return TestClient(app, base_url=base_url, headers=headers, client=(address, 12345))


def register(client: TestClient, email: str = "owner@example.com", name: str = "Test Owner"):
    response = client.post("/auth/register", json={"email": email, "name": name, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response
