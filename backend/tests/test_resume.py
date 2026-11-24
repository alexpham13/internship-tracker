import tempfile
import unittest
from pathlib import Path

import pymupdf

from backend.main import MAX_RESUME_SIZE
from backend.tests.auth_support import app_for, client_for, register


def make_pdf(*pages: str, encrypted: bool = False) -> bytes:
    with pymupdf.open() as document:
        for text in pages:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text)
        if encrypted:
            return document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="test-password")
        return document.tobytes()


class ResumeExtractionTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.client = self.enterContext(client_for(app_for(directory / "test.sqlite3")))
        register(self.client)

    def upload(self, content: bytes, filename: str = "resume.pdf", mime: str = "application/pdf"):
        return self.client.post("/resume/extract", files={"file": (filename, content, mime)})

    def test_extracts_multiple_pages_in_order_and_disables_caching(self):
        response = self.upload(make_pdf("Engineering Intern", "", "Python and SQL"), "Resume.PDF")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"text": "Engineering Intern\n\nPython and SQL"})
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.client.get("/applications").json(), [])

    def test_rejects_unsupported_file_types(self):
        pdf = make_pdf("Resume")
        for filename, content, mime in (
            ("resume.txt", pdf, "application/pdf"),
            ("resume.pdf", pdf, "text/plain"),
            ("resume.pdf", b"Not a PDF", "application/pdf"),
        ):
            with self.subTest(filename=filename, mime=mime, content=content[:10]):
                response = self.upload(content, filename, mime)
                self.assertEqual(response.status_code, 415, response.text)

    def test_accepts_limit_and_rejects_one_byte_over(self):
        pdf = make_pdf("Resume")
        # A PDF comment pads the upload while leaving its extractable text intact.
        at_limit = pdf + b"%" + b" " * (MAX_RESUME_SIZE - len(pdf) - 2) + b"\n"
        response = self.upload(at_limit, mime="application/octet-stream")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"text": "Resume"})
        response = self.upload(at_limit + b" ")
        self.assertEqual(response.status_code, 413, response.text)
        self.assertIn("5 MB", response.json()["detail"])

    def test_rejects_pdf_without_extractable_text(self):
        response = self.upload(make_pdf(""))
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("no extractable text", response.json()["detail"])

    def test_rejects_corrupt_pdf(self):
        response = self.upload(b"%PDF-1.7\nbroken\n")
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("Could not read", response.json()["detail"])

    def test_rejects_password_protected_pdf(self):
        response = self.upload(make_pdf("Resume", encrypted=True))
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("password", response.json()["detail"])

    def test_requires_multipart_file(self):
        response = self.client.post("/resume/extract")
        self.assertEqual(response.status_code, 422, response.text)
