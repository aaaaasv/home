import json
import tempfile
import unittest
from pathlib import Path

from src.infrastructure.adapters.file_panel_light import FilePanelLight


class FilePanelLightTestCase(unittest.IsolatedAsyncioTestCase):
    """
    The strip as the bot sees it: two small files the host service keeps.

    the unreadable case is the one with history. a half-written state file makes this return None, which
    publishes the lamp as unavailable and greys the tile out in the phone's home app — and for a while it
    did that without writing a single line anywhere, so the one time somebody reached for the tile and
    found it dead there was nothing to look at afterwards.
    """

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state_path = Path(self.directory.name) / "state.json"
        self.command_path = Path(self.directory.name) / "command.json"

    def build_light(self) -> FilePanelLight:
        return FilePanelLight(state_path=self.state_path, command_path=self.command_path)

    async def test_read_returns_what_the_service_published(self):
        self.state_path.write_text(json.dumps({"on": True, "percent": 20.0}))

        state = await self.build_light().read()

        self.assertEqual((state.is_on, state.brightness_percent), (True, 20.0))

    async def test_read_a_state_file_that_is_not_there_yet_says_it_does_not_know(self):
        state = await self.build_light().read()

        self.assertIsNone(state)

    async def test_read_a_half_written_state_file_says_it_does_not_know(self):
        """Exactly what a reader sees between the truncate and the write of a non-atomic publish."""
        self.state_path.write_text("")

        state = await self.build_light().read()

        self.assertIsNone(state)

    async def test_read_writes_a_warning_the_first_time_it_cannot_read(self):
        light = self.build_light()

        with self.assertLogs("src.infrastructure.adapters.file_panel_light", level="WARNING") as logged:
            await light.read()

        self.assertIn("goes unavailable", logged.output[0])

    async def test_read_does_not_repeat_the_warning_while_it_stays_unreadable(self):
        """A service that is genuinely down would otherwise write a line at every poll for as long as it is."""
        light = self.build_light()
        await light.read()

        with self.assertNoLogs("src.infrastructure.adapters.file_panel_light", level="WARNING"):
            await light.read()
            await light.read()

    async def test_read_says_so_once_the_state_can_be_read_again(self):
        light = self.build_light()
        await light.read()
        self.state_path.write_text(json.dumps({"on": False, "percent": 0.0}))

        with self.assertLogs("src.infrastructure.adapters.file_panel_light", level="INFO") as logged:
            await light.read()

        self.assertIn("readable again", logged.output[0])

    async def test_set_brightness_writes_the_command_the_service_reads(self):
        await self.build_light().set_brightness(20.0)

        self.assertEqual(json.loads(self.command_path.read_text()), {"percent": 20.0})

    async def test_set_brightness_keeps_the_value_inside_what_a_strip_can_do(self):
        await self.build_light().set_brightness(140.0)

        self.assertEqual(json.loads(self.command_path.read_text()), {"percent": 100.0})
