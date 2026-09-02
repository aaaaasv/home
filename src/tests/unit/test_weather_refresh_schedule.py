import unittest

from src.bot.handlers.weather.jobs import build_refresh_minutes


class BuildRefreshMinutesTestCase(unittest.TestCase):
    """
    The minutes at which the weather refresh fetches.

    open-meteo answered 503 to every request the bot made on :00 or :30 and to none made on :15
    or :45, so the guard is that no refresh minute lands on an hour or half-hour boundary.
    """

    def test_build_refresh_minutes_every_quarter_hour_avoids_the_boundary(self):
        minutes = build_refresh_minutes(15)

        self.assertEqual(minutes, "7,22,37,52")

    def test_build_refresh_minutes_never_lands_on_the_hour_or_half_hour(self):
        landed_on_boundary = [
            cadence for cadence in (5, 10, 15, 20, 30) if {"0", "30"} & set(build_refresh_minutes(cadence).split(","))
        ]

        self.assertEqual(landed_on_boundary, [])

    def test_build_refresh_minutes_keeps_the_requested_cadence(self):
        minutes = [int(minute) for minute in build_refresh_minutes(20).split(",")]

        self.assertEqual(minutes, [7, 27, 47])

    def test_build_refresh_minutes_wraps_past_the_hour_without_leaving_the_range(self):
        minutes = [int(minute) for minute in build_refresh_minutes(15, offset=55).split(",")]

        self.assertEqual(minutes, [55, 10, 25, 40])
