import unittest
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.modules.newspaper.print_window import find_window_start, is_inside_window, is_last_attempt

KYIV = ZoneInfo("Europe/Kyiv")
SATURDAY = 5
LUNCH = time(13, 0)
HALF_HOUR = timedelta(minutes=30)


def local(day: int, hour: int, minute: int = 0) -> datetime:
    # september 2026: the 19th is a saturday
    return datetime(2026, 9, day, hour, minute, tzinfo=KYIV)


class PrintWindowTestCase(unittest.TestCase):
    def test_find_window_start_on_saturday_afternoon_is_that_saturday_lunchtime(self):
        now = local(19, 15, 30)

        start = find_window_start(now, SATURDAY, LUNCH)

        self.assertEqual(start, local(19, 13))

    def test_find_window_start_on_saturday_morning_is_the_saturday_before(self):
        now = local(19, 10)

        start = find_window_start(now, SATURDAY, LUNCH)

        self.assertEqual(start, local(12, 13))

    def test_is_inside_window_on_sunday_evening_is_still_true(self):
        now = local(20, 20, 30)

        inside = is_inside_window(now, SATURDAY, LUNCH)

        self.assertTrue(inside)

    def test_is_inside_window_on_monday_morning_is_false(self):
        now = local(21, 8)

        inside = is_inside_window(now, SATURDAY, LUNCH)

        self.assertFalse(inside)

    def test_is_last_attempt_at_the_final_half_hour_of_sunday_is_true(self):
        now = local(20, 20, 30)

        last = is_last_attempt(now, SATURDAY, LUNCH, HALF_HOUR)

        self.assertTrue(last)

    def test_is_last_attempt_an_hour_before_the_window_closes_is_false(self):
        now = local(20, 20)

        last = is_last_attempt(now, SATURDAY, LUNCH, HALF_HOUR)

        self.assertFalse(last)
