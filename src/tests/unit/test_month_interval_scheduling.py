import unittest
from datetime import date
from types import SimpleNamespace

from src.common.constants import CareTaskType
from src.modules.plant_care.domain import (
    CareScheduleDetails,
    active_next_due,
    is_care_done_in_month,
    resolve_month_interval,
)

# Stonehenge (Conophytum friedrichiae): every twelve days in autumn, slowed to twenty-five over the winter,
# nothing at all from may to august. september-december carry no entry and fall back to the schedule's interval
STONEHENGE = {"1": 25, "2": 25, "3": 25, "4": 25, "5": None, "6": None, "7": None, "8": None}

# fertilizing, the old growing-season window written in the new shape: october-march silenced
GROWING_SEASON_APRIL_TO_SEPTEMBER = {"1": None, "2": None, "3": None, "10": None, "11": None, "12": None}


class ResolveMonthIntervalTestCase(unittest.TestCase):
    def test_resolve_month_interval_without_overrides_is_the_schedules_own_interval(self):
        self.assertEqual(resolve_month_interval(date(2027, 1, 15), 12, None), 12)

    def test_resolve_month_interval_for_a_month_with_no_entry_is_the_schedules_own_interval(self):
        self.assertEqual(resolve_month_interval(date(2026, 10, 15), 12, STONEHENGE), 12)

    def test_resolve_month_interval_for_a_slowed_month_is_the_slowed_interval(self):
        self.assertEqual(resolve_month_interval(date(2027, 1, 15), 12, STONEHENGE), 25)

    def test_resolve_month_interval_for_a_silenced_month_is_none(self):
        self.assertIsNone(resolve_month_interval(date(2027, 6, 15), 12, STONEHENGE))


class IsCareDoneInMonthTestCase(unittest.TestCase):
    def test_is_care_done_in_month_without_overrides_is_true(self):
        self.assertTrue(is_care_done_in_month(date(2027, 1, 15), None))

    def test_is_care_done_in_month_for_a_month_with_no_entry_is_true(self):
        self.assertTrue(is_care_done_in_month(date(2026, 10, 15), STONEHENGE))

    def test_is_care_done_in_month_for_a_slowed_month_is_true(self):
        self.assertTrue(is_care_done_in_month(date(2027, 1, 15), STONEHENGE))

    def test_is_care_done_in_month_for_a_silenced_month_is_false(self):
        self.assertFalse(is_care_done_in_month(date(2027, 6, 15), STONEHENGE))


class ActiveNextDueTestCase(unittest.TestCase):
    def test_active_next_due_without_overrides_returns_the_stored_date(self):
        self.assertEqual(active_next_due(date(2027, 1, 20), date(2027, 1, 10), None), date(2027, 1, 20))

    def test_active_next_due_in_an_active_month_keeps_a_date_already_in_the_run(self):
        self.assertEqual(active_next_due(date(2027, 1, 20), date(2027, 1, 15), STONEHENGE), date(2027, 1, 20))

    def test_active_next_due_in_a_silenced_month_points_to_the_next_active_month(self):
        self.assertEqual(active_next_due(date(2027, 4, 20), date(2027, 6, 10), STONEHENGE), date(2027, 9, 1))

    def test_active_next_due_after_a_silent_stretch_pulls_a_stale_date_up_to_the_stretch_start(self):
        self.assertEqual(active_next_due(date(2027, 4, 20), date(2027, 10, 5), STONEHENGE), date(2027, 9, 1))

    def test_active_next_due_in_a_run_crossing_the_new_year_keeps_the_stretch_start_in_the_previous_year(self):
        self.assertEqual(active_next_due(date(2026, 6, 4), date(2027, 1, 15), STONEHENGE), date(2026, 9, 1))

    def test_active_next_due_in_the_last_silenced_month_points_to_the_month_right_after_it(self):
        self.assertEqual(active_next_due(date(2027, 4, 20), date(2027, 8, 31), STONEHENGE), date(2027, 9, 1))

    def test_active_next_due_off_season_points_to_the_coming_season(self):
        self.assertEqual(
            active_next_due(date(2026, 10, 4), date(2027, 1, 15), GROWING_SEASON_APRIL_TO_SEPTEMBER), date(2027, 4, 1)
        )

    def test_active_next_due_at_season_start_pulls_an_overwintered_date_up_to_the_season_start(self):
        self.assertEqual(
            active_next_due(date(2026, 10, 4), date(2027, 4, 1), GROWING_SEASON_APRIL_TO_SEPTEMBER), date(2027, 4, 1)
        )


class CareScheduleDetailsMonthTestCase(unittest.TestCase):
    def build_schedule(self, next_due_on: date, overrides: dict[str, int | None] | None) -> SimpleNamespace:
        return SimpleNamespace(
            task_type=CareTaskType.WATERING,
            interval_days=12,
            next_due_on=next_due_on,
            last_performed_at=None,
            instructions="полий",
            month_interval_overrides=overrides,
            consecutive_postponements=0,
        )

    def test_from_schedule_in_a_slowed_month_reports_the_slowed_interval(self):
        schedule = self.build_schedule(date(2027, 1, 20), STONEHENGE)

        details = CareScheduleDetails.from_schedule(schedule, today=date(2027, 1, 15))

        self.assertEqual(details.interval_days, 25)
        self.assertEqual(details.next_due_on, date(2027, 1, 20))
        self.assertFalse(details.is_due)

    def test_from_schedule_in_a_silenced_month_is_not_due_and_waits_for_the_next_active_month(self):
        schedule = self.build_schedule(date(2027, 4, 20), STONEHENGE)

        details = CareScheduleDetails.from_schedule(schedule, today=date(2027, 6, 10))

        self.assertFalse(details.is_due)
        self.assertEqual(details.overdue_days, 0)
        self.assertEqual(details.next_due_on, date(2027, 9, 1))
        self.assertEqual(details.days_until_due, 83)

    def test_from_schedule_in_a_silenced_month_falls_back_to_the_schedules_own_interval(self):
        schedule = self.build_schedule(date(2027, 4, 20), STONEHENGE)

        details = CareScheduleDetails.from_schedule(schedule, today=date(2027, 6, 10))

        self.assertEqual(details.interval_days, 12)

    def test_from_schedule_at_the_end_of_a_silent_stretch_reads_a_stale_task_as_due_today(self):
        schedule = self.build_schedule(date(2027, 4, 20), STONEHENGE)

        details = CareScheduleDetails.from_schedule(schedule, today=date(2027, 9, 1))

        self.assertTrue(details.is_due)
        self.assertEqual(details.overdue_days, 0)
        self.assertEqual(details.next_due_on, date(2027, 9, 1))
