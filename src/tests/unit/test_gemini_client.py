import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.infrastructure.adapters.gemini_client import GeminiQuotaRefused, generate_content

ANSWER = {"candidates": [{"content": {"parts": [{"text": "так"}]}}]}


class StubGeminiHandler(BaseHTTPRequestHandler):
    """Answers each request with the next scripted status, then keeps repeating the last one."""

    def do_POST(self) -> None:  # noqa: N802 — the name is BaseHTTPRequestHandler's
        self.rfile.read(int(self.headers["Content-Length"]))
        index = min(len(self.server.requests), len(self.server.statuses) - 1)
        self.server.requests.append(self.path)
        status = self.server.statuses[index]
        body = json.dumps(ANSWER if status == 200 else {"error": {"message": "PerDay quota"}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        pass


class GenerateContentTestCase(unittest.IsolatedAsyncioTestCase):
    """An overloaded model is asked again; a broken request or a spent quota is not."""

    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), StubGeminiHandler)
        self.server.requests = []
        self.server.statuses = [200]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def call(self):
        return generate_content(
            api_key="test-key",
            model="gemini-test",
            body={"contents": []},
            purpose="Test call",
            timeout_seconds=2,
            retry_delays_seconds=(0, 0),
            url_template=f"http://127.0.0.1:{self.server.server_port}/models/{{model}}:generateContent",
        )

    async def test_generate_content_after_two_overloaded_refusals_returns_the_third_answer(self):
        self.server.statuses = [503, 503, 200]

        payload = await self.call()

        self.assertEqual(payload, ANSWER)
        self.assertEqual(len(self.server.requests), 3)

    async def test_generate_content_overloaded_on_every_attempt_returns_nothing(self):
        self.server.statuses = [503]

        payload = await self.call()

        self.assertIsNone(payload)
        self.assertEqual(len(self.server.requests), 3)

    async def test_generate_content_with_a_rejected_request_does_not_ask_again(self):
        self.server.statuses = [400]

        payload = await self.call()

        self.assertIsNone(payload)
        self.assertEqual(len(self.server.requests), 1)

    async def test_generate_content_with_the_quota_spent_raises_with_the_body_and_does_not_ask_again(self):
        self.server.statuses = [429]

        with self.assertRaises(GeminiQuotaRefused) as context:
            await self.call()

        self.assertEqual(context.exception.body, '{"error": {"message": "PerDay quota"}}')
        self.assertEqual(len(self.server.requests), 1)
