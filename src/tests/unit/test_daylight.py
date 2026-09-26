import unittest
from datetime import datetime, timedelta, timezone

from src.common.daylight import CIVIL_TWILIGHT_DEGREES, is_dark, solar_elevation_degrees

KYIV_LATITUDE = 50.45
KYIV_LONGITUDE = 30.52
EEST = timezone(timedelta(hours=3))


class DaylightTestCase(unittest.TestCase):
    """
    Darkness worked out from the sun rather than the clock — a fixed evening hour is wrong most of the year.

    checked against the published times for Kyiv on 26.09.2026: sunrise 06:57, sunset 18:52.
    """

    def elevation(self, moment: datetime) -> float:
        return solar_elevation_degrees(moment, KYIV_LATITUDE, KYIV_LONGITUDE)

    def test_the_sun_is_below_the_horizon_just_before_the_published_sunrise(self):
        self.assertLess(self.elevation(datetime(2026, 9, 26, 6, 45, tzinfo=EEST)), 0)

    def test_the_sun_is_above_the_horizon_just_after_the_published_sunrise(self):
        self.assertGreater(self.elevation(datetime(2026, 9, 26, 7, 10, tzinfo=EEST)), 0)

    def test_the_sun_is_above_the_horizon_just_before_the_published_sunset(self):
        self.assertGreater(self.elevation(datetime(2026, 9, 26, 18, 40, tzinfo=EEST)), 0)

    def test_the_sun_is_below_the_horizon_just_after_the_published_sunset(self):
        self.assertLess(self.elevation(datetime(2026, 9, 26, 19, 5, tzinfo=EEST)), 0)

    def test_midday_in_summer_stands_higher_than_midday_in_winter(self):
        summer = self.elevation(datetime(2026, 6, 21, 13, 30, tzinfo=EEST))
        winter = self.elevation(datetime(2026, 12, 21, 12, 30, tzinfo=EEST))

        self.assertGreater(summer - winter, 40)

    def test_an_hour_after_sunset_is_dark(self):
        self.assertTrue(is_dark(datetime(2026, 9, 26, 20, 0, tzinfo=EEST), KYIV_LATITUDE, KYIV_LONGITUDE))

    def test_the_middle_of_the_day_is_not_dark(self):
        self.assertFalse(is_dark(datetime(2026, 9, 26, 13, 0, tzinfo=EEST), KYIV_LATITUDE, KYIV_LONGITUDE))

    def test_dusk_is_not_dark_until_civil_twilight_is_past(self):
        """The sun has set but the sky is still bright — a hallway does not need the light yet."""
        just_after_sunset = datetime(2026, 9, 26, 19, 0, tzinfo=EEST)

        self.assertLess(self.elevation(just_after_sunset), 0)
        self.assertGreater(self.elevation(just_after_sunset), CIVIL_TWILIGHT_DEGREES)
        self.assertFalse(is_dark(just_after_sunset, KYIV_LATITUDE, KYIV_LONGITUDE))

    def test_a_summer_evening_is_still_light_when_a_winter_one_is_dark(self):
        nine_in_june = datetime(2026, 6, 21, 21, 0, tzinfo=EEST)
        six_in_december = datetime(2026, 12, 21, 18, 0, tzinfo=EEST)

        self.assertFalse(is_dark(nine_in_june, KYIV_LATITUDE, KYIV_LONGITUDE))
        self.assertTrue(is_dark(six_in_december, KYIV_LATITUDE, KYIV_LONGITUDE))
