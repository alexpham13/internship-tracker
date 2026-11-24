import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx2
from google.genai import errors

from backend.tests.auth_support import app_for, client_for, register

PATH = "/cover-letter/generate"
INPUT = {
    "resume_text": "Built a dashboard using Python.",
    "job_description": "Acme seeks a data intern to help develop dashboards.",
    "tone": "professional",
}


def gemini_result(payload):
    return SimpleNamespace(text=json.dumps(payload))


class CoverLetterTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.client = self.enterContext(client_for(app_for(directory / "cover-letter.sqlite3")))
        register(self.client)
        self.env = self.enterContext(patch.dict("os.environ", {
            "GEMINI_API_KEY": "mock-key",
            "GEMINI_MODEL": "configured-model",
        }))
        self.gemini = self.enterContext(patch("backend.resume_analysis.genai.Client"))
        self.generate = self.gemini.return_value.__enter__.return_value.models.generate_content

    def test_returns_checked_draft_for_each_tone_and_accepts_word_count_boundaries(self):
        for tone, length in (("professional", 250), ("enthusiastic", 300), ("concise", 350)):
            with self.subTest(tone=tone):
                self.generate.reset_mock()
                fields = {**INPUT, "tone": tone}
                letter = " ".join(["draft"] * length)
                self.generate.side_effect = [
                    gemini_result({"cover_letter": letter}),
                    gemini_result({"supported": True}),
                ]
                response = self.client.post(PATH, json=fields)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json(), {"cover_letter": letter})
                self.assertEqual(response.headers["cache-control"], "no-store")
                generation, review = [call.kwargs for call in self.generate.call_args_list]
                self.assertEqual(generation["model"], "configured-model")
                self.assertEqual(review["model"], "configured-model")
                self.assertEqual(self.gemini.call_args.kwargs["api_key"], "mock-key")
                self.assertEqual(json.loads(generation["contents"]), fields)
                self.assertIn("Never invent", generation["config"].system_instruction)
                self.assertEqual(json.loads(review["contents"]), {
                    "resume_text": INPUT["resume_text"],
                    "job_description": INPUT["job_description"],
                    "cover_letter": letter,
                })
        self.assertEqual(self.client.get("/applications").json(), [])

    def test_invalid_inputs_do_not_echo_private_content_or_call_gemini(self):
        for fields in (
            {**INPUT, "resume_text": " "},
            {**INPUT, "resume_text": {"text": "private sample"}},
            {**INPUT, "job_description": "private sample" * 3_000},
            {**INPUT, "tone": "private sample"},
            {**INPUT, "extra": "private sample"},
            {key: value for key, value in INPUT.items() if key != "tone"},
        ):
            with self.subTest(keys=list(fields)):
                response = self.client.post(PATH, json=fields)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertNotIn("private sample", response.text)
        self.gemini.assert_not_called()

    def test_rejects_invalid_drafts_before_review(self):
        for result in (
            gemini_result({"cover_letter": "word " * 249}),
            gemini_result({"cover_letter": "word " * 351}),
            gemini_result({"cover_letter": 123}),
            SimpleNamespace(text="private sample"),
            SimpleNamespace(text=None),
        ):
            with self.subTest(result=result):
                self.generate.reset_mock()
                self.generate.return_value = result
                response = self.client.post(PATH, json=INPUT)
                self.assertEqual(response.status_code, 502)
                self.assertNotIn("private sample", response.text)
                self.generate.assert_called_once()

    def test_does_not_return_drafts_that_fail_grounding_review(self):
        draft = "I achieved a private sample. " + "word " * 250
        for result in ({"supported": False}, {"supported": "true"}):
            with self.subTest(result=result):
                self.generate.side_effect = [
                    gemini_result({"cover_letter": draft}),
                    gemini_result(result),
                ]
                response = self.client.post(PATH, json=INPUT)
                self.assertEqual(response.status_code, 502)
                self.assertNotIn("private sample", response.text)

    def test_transient_503_retries_each_stage_without_regenerating_during_review(self):
        unavailable = errors.APIError(503, {"error": {"message": "private sample mock-key"}})
        draft = "draft " * 250
        self.generate.side_effect = [
            unavailable, unavailable, gemini_result({"cover_letter": draft}),
            unavailable, unavailable, gemini_result({"supported": True}),
        ]
        with patch("backend.resume_analysis.sleep") as sleep:
            with self.assertLogs("backend.resume_analysis", level="WARNING") as logs:
                response = self.client.post(PATH, json=INPUT)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([call.args for call in sleep.call_args_list], [(1,), (2,), (1,), (2,)])
        calls = [call.kwargs for call in self.generate.call_args_list]
        self.assertEqual(len(calls), 6)
        self.assertEqual([json.loads(call["contents"]) for call in calls[:3]], [INPUT] * 3)
        self.assertEqual([json.loads(call["contents"])["cover_letter"] for call in calls[3:]], [draft.strip()] * 3)
        self.assertTrue(all(call["model"] == "configured-model" for call in calls))
        for call in self.gemini.call_args_list:
            options = call.kwargs["http_options"]
            self.assertEqual(options.timeout, 30_000)
            self.assertEqual(options.retry_options.attempts, 1)
        log = "\n".join(logs.output)
        self.assertIn("cover letter generation retrying", log)
        self.assertIn("cover letter grounding verification retrying", log)
        self.assertNotIn("private sample", log)
        self.assertNotIn("mock-key", log)

    def test_persistent_503_returns_unavailable_and_identifies_failed_stage(self):
        unavailable = errors.APIError(503, {"error": {"message": "private sample mock-key"}})
        for stage, completed in (
            ("generation", []),
            ("grounding verification", [gemini_result({"cover_letter": "draft " * 250})]),
        ):
            with self.subTest(stage=stage):
                self.generate.reset_mock()
                self.generate.side_effect = [*completed, unavailable, unavailable, unavailable]
                with patch("backend.resume_analysis.sleep") as sleep:
                    with self.assertLogs("backend.resume_analysis", level="WARNING") as logs:
                        response = self.client.post(PATH, json=INPUT)

                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {
                    "detail": "Google Gemini is temporarily unavailable. Please try again in a moment.",
                })
                self.assertEqual(self.generate.call_count, len(completed) + 3)
                self.assertEqual([call.args for call in sleep.call_args_list], [(1,), (2,)])
                self.assertIn(f"cover letter {stage} failed: provider_unavailable", logs.output[-1])

    def test_missing_key(self):
        self.env["GEMINI_API_KEY"] = ""
        response = self.client.post(PATH, json=INPUT)
        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.json()["detail"])
        self.gemini.assert_not_called()

    def test_provider_failures_are_sanitized(self):
        for error, status in (
            (errors.APIError(429, {"error": {"message": "private sample mock-key"}}), 429),
            (httpx2.ReadTimeout("private sample"), 504),
            (httpx2.ConnectError("private sample"), 502),
        ):
            with self.subTest(status=status):
                self.generate.side_effect = error
                with self.assertLogs("backend.resume_analysis", level="WARNING") as logs:
                    response = self.client.post(PATH, json=INPUT)
                self.assertEqual(response.status_code, status)
                for secret in ("private sample", "mock-key"):
                    self.assertNotIn(secret, response.text)
                    self.assertNotIn(secret, "\n".join(logs.output))
                self.generate.assert_called_once()
                self.generate.reset_mock()
