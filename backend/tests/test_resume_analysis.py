import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx2
from google.genai import errors

from backend.tests.auth_support import app_for, client_for, register


INPUT = {
    "resume_text": "Built a dashboard\nusing Python.",
    "job_description": "Seeking a Python and SQL intern.",
}
RESULT = {
    "match_score": 70,
    "overall_assessment": "The resume demonstrates Python experience.",
    "matching_skills": ["Python"],
    "missing_skills": ["SQL"],
    "strengths": ["Dashboard development"],
    "areas_for_improvement": ["Explain how the dashboard was used."],
    "bullet_improvements": [{
        "source_text": "Built a dashboard using Python.",
        "suggested_text": "Developed a Python dashboard.",
    }],
    "recommendations": ["Add SQL work if you have relevant experience."],
}


class ResumeAnalysisTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.client = self.enterContext(client_for(app_for(directory / "analysis.sqlite3")))
        register(self.client)
        self.env = self.enterContext(patch.dict("os.environ", {
            "GEMINI_API_KEY": "mock-key",
            "GEMINI_MODEL": "configured-model",
        }))
        self.gemini = self.enterContext(patch("backend.resume_analysis.genai.Client"))
        self.generate = self.gemini.return_value.__enter__.return_value.models.generate_content

    def test_returns_validated_json_and_omits_unsupported_bullet_sources(self):
        result = {**RESULT, "bullet_improvements": [
            *RESULT["bullet_improvements"],
            {"source_text": "Managed 12 people", "suggested_text": "Led a team of 12."},
        ]}
        self.generate.return_value = SimpleNamespace(text=json.dumps(result))
        response = self.client.post("/resume/analyze", json=INPUT)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), RESULT)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.client.get("/applications").json(), [])
        self.gemini.assert_called_once()
        self.assertEqual(self.gemini.call_args.kwargs["api_key"], "mock-key")
        self.assertFalse(self.gemini.call_args.kwargs["vertexai"])
        call = self.generate.call_args.kwargs
        self.assertEqual(call["model"], "configured-model")
        self.assertEqual(json.loads(call["contents"]), INPUT)
        self.assertEqual(call["config"].response_mime_type, "application/json")
        self.assertIn("match_score", call["config"].response_json_schema["required"])
        self.assertIn("Do not infer or invent", call["config"].system_instruction)

    def test_uses_supported_default_when_model_is_blank(self):
        self.env["GEMINI_MODEL"] = " "
        self.generate.return_value = SimpleNamespace(text=json.dumps(RESULT))
        response = self.client.post("/resume/analyze", json=INPUT)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.generate.call_args.kwargs["model"], "gemini-3.5-flash-lite")

    def test_rejects_invalid_inputs_without_echoing_content(self):
        for fields in (
            {**INPUT, "resume_text": "   "},
            {**INPUT, "job_description": 123},
            {**INPUT, "resume_text": "private sample " * 3_000},
            {**INPUT, "unexpected": "private sample"},
            {"resume_text": INPUT["resume_text"]},
        ):
            with self.subTest(fields=list(fields)):
                response = self.client.post("/resume/analyze", json=fields)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("private sample", response.text)
                self.assertNotIn("input", response.text)
        self.gemini.assert_not_called()

    def test_missing_key(self):
        self.env["GEMINI_API_KEY"] = " "
        response = self.client.post("/resume/analyze", json=INPUT)
        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.json()["detail"])
        self.gemini.assert_not_called()

    def test_provider_errors_are_mapped_without_leaking_details(self):
        for code, reason, status, message, category in (
            (400, "API_KEY_INVALID", 503, "credentials", "credentials_rejected"),
            (403, "PERMISSION_DENIED", 503, "credentials", "credentials_rejected"),
            (404, "MODEL_NOT_FOUND", 503, "GEMINI_MODEL", "model_unavailable"),
            (429, "RESOURCE_EXHAUSTED", 429, "rate limit", "quota_or_rate_limit"),
            (504, "DEADLINE_EXCEEDED", 504, "too long", "provider_timeout"),
            (500, "INTERNAL", 502, "could not complete", "upstream_error"),
        ):
            with self.subTest(code=code):
                self.generate.side_effect = errors.APIError(code, {
                    "error": {"message": "private sample mock-key", "details": [{"reason": reason}]},
                })
                with self.assertLogs("backend.resume_analysis", level="WARNING") as logs:
                    response = self.client.post("/resume/analyze", json=INPUT)
                self.assertEqual(response.status_code, status, response.text)
                self.assertIn(message, response.json()["detail"])
                self.assertNotIn("private sample", response.text)
                self.assertIn(f"{category} (provider_status={code})", logs.output[0])
                self.assertNotIn("private sample", logs.output[0])
                self.assertNotIn("mock-key", logs.output[0])

    def test_logs_schema_rejection_without_provider_message(self):
        self.generate.side_effect = errors.APIError(400, {
            "error": {"message": "Invalid schema: private sample mock-key"},
        })
        with self.assertLogs("backend.resume_analysis", level="WARNING") as logs:
            response = self.client.post("/resume/analyze", json=INPUT)
        self.assertEqual(response.status_code, 502, response.text)
        self.assertIn("schema_rejected (provider_status=400)", logs.output[0])
        self.assertNotIn("private sample", logs.output[0])
        self.assertNotIn("mock-key", logs.output[0])

    def test_transport_timeout_and_connection_errors(self):
        for error, status in (
            (httpx2.ReadTimeout("private sample"), 504),
            (httpx2.ConnectError("private sample"), 502),
        ):
            with self.subTest(error=type(error).__name__):
                self.generate.side_effect = error
                response = self.client.post("/resume/analyze", json=INPUT)
                self.assertEqual(response.status_code, status, response.text)
                self.assertNotIn("private sample", response.text)

    def test_rejects_malformed_or_incomplete_model_output(self):
        for output in (
            None,
            "private sample",
            json.dumps({**RESULT, "match_score": 101}),
            json.dumps({**RESULT, "match_score": "70"}),
            json.dumps({**RESULT, "matching_skills": ["   "]}),
            json.dumps({"match_score": 70}),
        ):
            with self.subTest(output_type=type(output).__name__):
                self.generate.return_value = SimpleNamespace(text=output)
                with self.assertLogs("backend.resume_analysis", level="WARNING") as logs:
                    response = self.client.post("/resume/analyze", json=INPUT)
                self.assertEqual(response.status_code, 502, response.text)
                self.assertIn("invalid analysis", response.json()["detail"])
                self.assertNotIn("private sample", response.text)
                self.assertIn("validation_error (codes=", logs.output[0])
                self.assertNotIn("private sample", logs.output[0])
