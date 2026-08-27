import unittest
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from src.infrastructure.adapters.yasno_schedule_provider import parse_outage_outlook, parse_outage_schedule
from src.modules.power.domain import OutageInterval, OutageScheduleStatus

KYIV = ZoneInfo("Europe/Kyiv")

# the real endpoint's envelope (confirmed live 2026-08-11): one object per group, each with today/tomorrow blocks
# and a per-group updatedOn; slots are {start, end, type} in minutes from midnight, "Definite" == power off. Today's
# 16:00–19:30 outage arrives as two touching Definite slots the parser must fuse into one interval
SAMPLE = {
    "2.1": {
        "today": {
            "slots": [
                {"start": 0, "end": 480, "type": "NotPlanned"},
                {"start": 480, "end": 630, "type": "Definite"},
                {"start": 630, "end": 960, "type": "NotPlanned"},
                {"start": 960, "end": 1080, "type": "Definite"},
                {"start": 1080, "end": 1170, "type": "Definite"},
                {"start": 1170, "end": 1440, "type": "NotPlanned"},
            ],
            "date": "2026-08-11T00:00:00+03:00",
            "status": "ScheduleApplies",
        },
        "tomorrow": {"slots": [], "date": "2026-08-12T00:00:00+03:00", "status": "WaitingForSchedule"},
        "updatedOn": "2026-08-11T09:15:00+00:00",
    },
    "1.1": {
        "today": {"slots": [], "date": "2026-08-11T00:00:00+03:00", "status": "NoOutages"},
        "tomorrow": {"slots": [], "date": "2026-08-12T00:00:00+03:00", "status": "WaitingForSchedule"},
        "updatedOn": "2026-08-11T09:15:00+00:00",
    },
}


class ParseOutageScheduleTestCase(unittest.TestCase):
    def test_parse_schedule_with_definite_slots_merges_touching_intervals(self):
        schedule = parse_outage_schedule(SAMPLE, "2.1", "today")

        self.assertEqual(schedule.day, date(2026, 8, 11))
        self.assertEqual(schedule.status, OutageScheduleStatus.SCHEDULE_APPLIES)
        self.assertEqual(
            schedule.off_intervals,
            (OutageInterval(480, 630), OutageInterval(960, 1170)),
        )
        self.assertEqual(schedule.updated_on, datetime(2026, 8, 11, 9, 15, tzinfo=timezone.utc))
        self.assertTrue(schedule.has_outages)

    def test_parse_schedule_exposes_intervals_as_local_wall_clock_times(self):
        schedule = parse_outage_schedule(SAMPLE, "2.1", "today")

        first, second = schedule.off_intervals

        self.assertEqual((first.start, first.end), (time(8, 0), time(10, 30)))
        self.assertEqual((second.start, second.end), (time(16, 0), time(19, 30)))

    def test_parse_schedule_with_no_outages_has_empty_intervals(self):
        schedule = parse_outage_schedule(SAMPLE, "1.1", "today")

        self.assertEqual(schedule.status, OutageScheduleStatus.NO_OUTAGES)
        self.assertEqual(schedule.off_intervals, ())
        self.assertFalse(schedule.has_outages)

    def test_parse_schedule_for_waiting_tomorrow_reports_waiting_status(self):
        schedule = parse_outage_schedule(SAMPLE, "2.1", "tomorrow")

        self.assertEqual(schedule.day, date(2026, 8, 12))
        self.assertEqual(schedule.status, OutageScheduleStatus.WAITING_FOR_SCHEDULE)
        self.assertEqual(schedule.off_intervals, ())

    def test_parse_schedule_for_unknown_group_returns_none(self):
        schedule = parse_outage_schedule(SAMPLE, "99.9", "today")

        self.assertIsNone(schedule)

    def test_parse_schedule_with_unfamiliar_status_falls_back_to_unknown(self):
        payload = {
            "2.1": {
                "today": {"slots": [], "date": "2026-08-11T00:00:00+03:00", "status": "SomethingNew"},
                "updatedOn": "2026-08-11T09:15:00+00:00",
            }
        }

        schedule = parse_outage_schedule(payload, "2.1", "today")

        self.assertEqual(schedule.status, OutageScheduleStatus.UNKNOWN)


class OutageScheduleQueriesTestCase(unittest.TestCase):
    def setUp(self):
        self.schedule = parse_outage_schedule(SAMPLE, "2.1", "today")

    def test_next_off_interval_before_first_outage_returns_first(self):
        upcoming = self.schedule.next_off_interval(datetime(2026, 8, 11, 7, 0, tzinfo=KYIV))

        self.assertEqual(upcoming, OutageInterval(480, 630))

    def test_next_off_interval_between_outages_returns_the_later_one(self):
        upcoming = self.schedule.next_off_interval(datetime(2026, 8, 11, 12, 0, tzinfo=KYIV))

        self.assertEqual(upcoming, OutageInterval(960, 1170))

    def test_next_off_interval_after_last_outage_returns_none(self):
        upcoming = self.schedule.next_off_interval(datetime(2026, 8, 11, 20, 0, tzinfo=KYIV))

        self.assertIsNone(upcoming)

    def test_is_off_at_inside_an_outage_is_true(self):
        self.assertTrue(self.schedule.is_off_at(datetime(2026, 8, 11, 16, 30, tzinfo=KYIV)))

    def test_is_off_at_the_exclusive_end_is_false(self):
        self.assertFalse(self.schedule.is_off_at(datetime(2026, 8, 11, 19, 30, tzinfo=KYIV)))

    def test_is_off_at_between_outages_is_false(self):
        self.assertFalse(self.schedule.is_off_at(datetime(2026, 8, 11, 12, 0, tzinfo=KYIV)))


class ParseOutageOutlookTestCase(unittest.TestCase):
    def test_parse_outlook_returns_both_days(self):
        outlook = parse_outage_outlook(SAMPLE, "2.1")

        self.assertEqual(outlook.today.day, date(2026, 8, 11))
        self.assertTrue(outlook.today.has_outages)
        self.assertEqual(outlook.tomorrow.status, OutageScheduleStatus.WAITING_FOR_SCHEDULE)

    def test_parse_outlook_for_unknown_group_returns_none(self):
        self.assertIsNone(parse_outage_outlook(SAMPLE, "99.9"))


if __name__ == "__main__":
    unittest.main()
