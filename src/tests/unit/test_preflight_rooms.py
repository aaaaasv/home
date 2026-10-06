import logging
import unittest

from src.bot.preflight import verify_sensored_rooms
from src.common.config import Settings


class VerifySensoredRoomsTestCase(unittest.TestCase):
    """
    A room named in one setting and spelled differently in another costs a temperature and reports nothing.

    this cost a live card its reading: the air conditioner was configured for «вітальня» while every sensor
    called the same room «кухня-вітальня», and the card simply went blank — no error, nothing in the log.
    """

    def build_settings(self, **overrides) -> Settings:
        return Settings(
            TELEGRAM_BOT_TOKEN="123:abc",
            SENSOR_ROOMS='{"temp-kitchen": "кухня-вітальня", "temp-bedroom": "спальня"}',
            **overrides,
        )

    def test_verify_sensored_rooms_with_a_room_no_sensor_covers_warns(self):
        settings = self.build_settings(AIR_CONDITIONER_ROOM="вітальня")

        with self.assertLogs("src.bot.preflight", level=logging.WARNING) as logs:
            verify_sensored_rooms(settings)

        self.assertEqual(
            logs.output,
            [
                "WARNING:src.bot.preflight:AIR_CONDITIONER_ROOM is 'вітальня', which no sensor covers "
                "(кухня-вітальня, спальня) — the card will show no temperature"
            ],
        )

    def test_verify_sensored_rooms_with_a_covered_room_says_nothing(self):
        settings = self.build_settings(AIR_CONDITIONER_ROOM="кухня-вітальня")

        with self.assertNoLogs("src.bot.preflight", level=logging.WARNING):
            verify_sensored_rooms(settings)

    def test_verify_sensored_rooms_without_any_sensors_says_nothing(self):
        settings = Settings(TELEGRAM_BOT_TOKEN="123:abc", AIR_CONDITIONER_ROOM="вітальня")

        with self.assertNoLogs("src.bot.preflight", level=logging.WARNING):
            verify_sensored_rooms(settings)
