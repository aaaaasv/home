import unittest
from datetime import date
from types import SimpleNamespace

from src.common.constants import CareTaskType
from src.modules.plant_care.domain import CareScheduleDetails, is_in_growing_season, seasonal_next_due


class IsInGrowingSeasonTestCase(unittest.TestCase):
    def test_is_in_growing_season_without_a_window_is_always_true(self):
        self.assertTrue(is_in_growing_season(date(2027, 1, 15), None, None))

    def test_is_in_growing_season_inside_the_window_is_true(self):
        self.assertTrue(is_in_growing_season(date(2027, 7, 1), 4, 9))

    def test_is_in_growing_season_on_the_boundary_month_is_true(self):
        self.assertTrue(is_in_growing_season(date(2027, 9, 30), 4, 9))

    def test_is_in_growing_season_outside_the_window_is_false(self):
        self.assertFalse(is_in_growing_season(date(2027, 1, 15), 4, 9))


class SeasonalNextDueTestCase(unittest.TestCase):
    def test_seasonal_next_due_without_a_window_returns_the_stored_date(self):
        self.assertEqual(seasonal_next_due(date(2027, 1, 20), date(2027, 1, 10), None, None), date(2027, 1, 20))

    def test_seasonal_next_due_in_season_keeps_a_due_date_already_in_the_window(self):
        self.assertEqual(seasonal_next_due(date(2027, 7, 9), date(2027, 7, 12), 4, 9), date(2027, 7, 9))

    def test_seasonal_next_due_in_season_pulls_an_overwintered_date_up_to_the_season_start(self):
        self.assertEqual(seasonal_next_due(date(2026, 10, 4), date(2027, 4, 1), 4, 9), date(2027, 4, 1))

    def test_seasonal_next_due_after_the_season_ends_points_to_next_spring(self):
        self.assertEqual(seasonal_next_due(date(2026, 10, 4), date(2026, 11, 20), 4, 9), date(2027, 4, 1))

    def test_seasonal_next_due_before_the_season_starts_points_to_this_spring(self):
        self.assertEqual(seasonal_next_due(date(2027, 3, 20), date(2027, 2, 10), 4, 9), date(2027, 4, 1))


class CareScheduleDetailsSeasonTestCase(unittest.TestCase):
    def build_schedule(self, next_due_on: date, start_month: int | None, end_month: int | None) -> SimpleNamespace:
        return SimpleNamespace(
            task_type=CareTaskType.FERTILIZING,
            interval_days=30,
            next_due_on=next_due_on,
            last_performed_at=None,
            instructions="годуй",
            season_start_month=start_month,
            season_end_month=end_month,
        )

    def test_from_schedule_off_season_is_not_due_and_points_to_next_spring(self):
        schedule = self.build_schedule(date(2026, 10, 4), 4, 9)

        details = CareScheduleDetails.from_schedule(schedule, today=date(2027, 1, 15))

        self.assertFalse(details.is_due)
        self.assertEqual(details.overdue_days, 0)
        self.assertEqual(details.next_due_on, date(2027, 4, 1))
        self.assertEqual(details.days_until_due, 76)

    def test_from_schedule_at_season_start_reads_an_overwintered_task_as_due_today(self):
        schedule = self.build_schedule(date(2026, 10, 4), 4, 9)

        details = CareScheduleDetails.from_schedule(schedule, today=date(2027, 4, 1))

        self.assertTrue(details.is_due)
        self.assertEqual(details.overdue_days, 0)
        self.assertEqual(details.next_due_on, date(2027, 4, 1))
