import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.infrastructure.adapters.x728_pi_ups import X728PiUps

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


class X728PiUpsTestCase(unittest.IsolatedAsyncioTestCase):
    """
    The bot reads what the host agent publishes, so every way that file can lie has to end in silence.

    a wrong answer here is a push at three in the morning saying the light came back when it did not.
    """

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state_path = Path(self.directory.name) / "state.json"
        self.ups = X728PiUps(state_path=str(self.state_path), stale_after=timedelta(seconds=120))

    def publish(self, **overrides) -> None:
        published = dict(
            mains_present=True,
            battery_volts=4.175,
            battery_percent=99.1,
            as_of=NOW.isoformat(),
        )
        published.update(overrides)
        self.state_path.write_text(json.dumps(published))

    async def read(self):
        with patch("src.infrastructure.adapters.x728_pi_ups.current_time", return_value=NOW):
            return await self.ups.read_state()

    async def test_read_state_with_a_fresh_reading_returns_what_the_agent_published(self):
        self.publish(mains_present=False, battery_volts=3.78, battery_percent=45.0)

        state = await self.read()

        self.assertEqual(
            (state.mains_present, state.battery_volts, state.battery_percent, state.as_of),
            (False, 3.78, 45.0, NOW),
        )

    async def test_read_state_with_no_file_at_all_returns_nothing(self):
        state = await self.read()

        self.assertIsNone(state)

    async def test_read_state_with_a_reading_older_than_the_stale_window_returns_nothing(self):
        self.publish(as_of=(NOW - timedelta(seconds=121)).isoformat())

        state = await self.read()

        self.assertIsNone(state)

    async def test_read_state_with_a_reading_at_the_edge_of_the_stale_window_is_still_trusted(self):
        self.publish(as_of=(NOW - timedelta(seconds=120)).isoformat())

        state = await self.read()

        self.assertTrue(state.mains_present)

    async def test_read_state_with_a_truncated_file_returns_nothing(self):
        self.state_path.write_text('{"mains_present": tr')

        state = await self.read()

        self.assertIsNone(state)

    async def test_read_state_with_a_field_missing_returns_nothing(self):
        self.publish()
        published = json.loads(self.state_path.read_text())
        del published["battery_volts"]
        self.state_path.write_text(json.dumps(published))

        state = await self.read()

        self.assertIsNone(state)

    async def test_read_state_with_an_unparsable_timestamp_returns_nothing(self):
        self.publish(as_of="just now")

        state = await self.read()

        self.assertIsNone(state)
