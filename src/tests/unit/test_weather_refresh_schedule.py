import unittest

from src.bot.handlers.weather.jobs import build_refresh_minutes
from src.common.config import Settings
from src.infrastructure.adapters.open_meteo_weather_provider import WEATHER_RECENT_MAX_AGE_SECONDS


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


class DigestFetchWindowTestCase(unittest.TestCase):
    """
    The digest's own fetch is the one that decides whether the day has a forecast at all, so it gets the same
    protection the refreshes already had — and a fallback close enough behind it to matter.

    both guards come from one morning: on 10.09.2026 the digest fired at exactly 08:00, all three attempts came
    back 503, and the last good reading was 22:52 the night before — nine hours past the fallback's reach.
    """

    def setUp(self):
        self.settings = Settings(TELEGRAM_BOT_TOKEN="x", TELEGRAM_ALLOWED_USER_IDS="1", TELEGRAM_REMINDER_CHAT_ID=-1)

    def test_the_digest_never_fires_on_the_hour_or_half_hour_where_open_meteo_refuses(self):
        digest_minute = self.settings.weather_digest_time.minute

        self.assertNotIn(digest_minute, (0, 30))

    def test_the_refresh_window_opens_before_the_digest_rather_than_with_it(self):
        opens_at = self.settings.WEATHER_REFRESH_START_HOUR

        self.assertLess(opens_at, self.settings.weather_digest_time.hour)

    def test_the_last_refresh_before_the_digest_is_recent_enough_to_stand_in_for_it(self):
        digest = self.settings.weather_digest_time
        cron_minutes = build_refresh_minutes(self.settings.WEATHER_REFRESH_MINUTES).split(",")
        last_refresh_minute = max(int(minute) for minute in cron_minutes)

        gap_minutes = (digest.hour * 60 + digest.minute) - ((digest.hour - 1) * 60 + last_refresh_minute)

        self.assertLess(gap_minutes * 60, WEATHER_RECENT_MAX_AGE_SECONDS)
