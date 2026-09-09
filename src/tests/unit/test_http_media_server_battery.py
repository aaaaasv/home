import json
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from src.infrastructure.adapters.http_media_server_battery import HttpMediaServerBattery

NOW = datetime(2026, 9, 9, 12, 40, tzinfo=timezone.utc)


class StubBatteryHandler(BaseHTTPRequestHandler):
    """Serves whatever the test put on the server, so the adapter is exercised over a real socket."""

    def do_GET(self) -> None:  # noqa: N802 — the name is BaseHTTPRequestHandler's
        status, body = self.server.reply
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        pass


class HttpMediaServerBatteryTestCase(unittest.IsolatedAsyncioTestCase):
    """
    Every way the box can answer wrongly has to end in None, because the alternative is a fabricated row.

    a laptop halted for the blackout, a caching proxy in the way, a truncated body — none of those are
    "the battery is fine", and a board that drew them as numbers would be worse than one that drew nothing.
    """

    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), StubBatteryHandler)
        self.reply(200, self.published())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.battery = HttpMediaServerBattery(
            url=f"http://127.0.0.1:{self.server.server_port}/battery",
            timeout_seconds=1.0,
            stale_after=timedelta(seconds=120),
        )

    def published(self, **overrides) -> dict:
        reading = dict(
            on_mains=True,
            is_charging=False,
            charge_percent=64.0,
            energy_watt_hours=20.194,
            power_watts=0.0,
            as_of=NOW.isoformat(),
        )
        reading.update(overrides)
        return reading

    def reply(self, status: int, body) -> None:
        self.server.reply = (status, body if isinstance(body, bytes) else json.dumps(body).encode())

    async def read(self):
        with patch("src.infrastructure.adapters.http_media_server_battery.current_time", return_value=NOW):
            return await self.battery.read_state()

    async def test_read_state_with_a_fresh_reading_returns_what_the_box_published(self):
        self.reply(200, self.published(on_mains=False, is_charging=False, power_watts=10.0))

        state = await self.read()

        self.assertEqual(
            (state.on_mains, state.is_charging, state.charge_percent, state.power_watts, state.as_of),
            (False, False, 64.0, 10.0, NOW),
        )

    async def test_read_state_with_a_reading_older_than_the_stale_window_returns_nothing(self):
        self.reply(200, self.published(as_of=(NOW - timedelta(seconds=121)).isoformat()))

        state = await self.read()

        self.assertIsNone(state)

    async def test_read_state_with_a_reading_at_the_edge_of_the_stale_window_is_still_trusted(self):
        self.reply(200, self.published(as_of=(NOW - timedelta(seconds=120)).isoformat()))

        state = await self.read()

        self.assertEqual(state.charge_percent, 64.0)

    async def test_read_state_when_the_box_cannot_read_its_own_sysfs_returns_nothing(self):
        self.reply(503, b"")

        state = await self.read()

        self.assertIsNone(state)

    async def test_read_state_with_a_truncated_body_returns_nothing(self):
        self.reply(200, b'{"on_mains": tr')

        state = await self.read()

        self.assertIsNone(state)

    async def test_read_state_with_a_field_missing_returns_nothing(self):
        incomplete = self.published()
        del incomplete["power_watts"]
        self.reply(200, incomplete)

        state = await self.read()

        self.assertIsNone(state)

    async def test_read_state_with_the_box_off_the_network_returns_nothing(self):
        # shutdown alone only stops serving; the port has to be released for the connection to be refused
        self.server.shutdown()
        self.server.server_close()

        state = await self.read()

        self.assertIsNone(state)
