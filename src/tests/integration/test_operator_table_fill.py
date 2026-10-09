import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.infrastructure.adapters.dtek_outage_mirror import parse_group_intervals
from src.modules.power.domain import OutageInterval, OutageOutlook, OutageSchedule, OutageScheduleStatus
from src.modules.power.services.filled_outage_schedule_provider import FilledOutageScheduleProvider

KYIV = ZoneInfo("Europe/Kyiv")
GROUP = "23.1"
TODAY = date(2026, 10, 9)
TOMORROW = date(2026, 10, 10)
STALE_AFTER = timedelta(hours=30)


def published_hours_ago(hours: float) -> str:
    """Freshness is measured against the wall clock, so a fixed timestamp would pass only on the day it was written."""
    return (datetime.now(KYIV) - timedelta(hours=hours)).isoformat()


def build_mirror(intervals: list[dict], updated_at: str | None = None, ok: bool = True) -> dict:
    updated_at = updated_at if updated_at is not None else published_hours_ago(2)
    return {
        "updatedAt": updated_at,
        "status": {"ok": ok, "code": "ok" if ok else "fetch_failed"},
        "schedules": {GROUP: {"group": 23, "subgroup": 1, "name": "Черга 23.1", "intervals": intervals}},
    }


def off(start: str, end: str, origin: str = "fact", kind: str = "off") -> dict:
    return {"start": start, "end": end, "kind": kind, "type": "planned", "origin": origin}


class ParseOperatorTableTestCase(unittest.TestCase):
    """
    One group's hours out of the mirrored operator table, and every reading that must not be trusted.

    the table is the only source with hours during emergency shutdowns, so it has to be read — but it is a
    third party mirroring a site behind a bot wall, and it answers 200 with yesterday's table when it freezes.
    """

    def parse(self, payload: dict, day: date = TODAY):
        return parse_group_intervals(payload, GROUP, day, KYIV, STALE_AFTER)

    def test_parse_the_days_own_hours_are_returned_as_minutes_from_midnight(self):
        payload = build_mirror([off("2026-10-09T08:00:00+03:00", "2026-10-09T11:00:00+03:00")])

        intervals = self.parse(payload)

        self.assertEqual(intervals, (OutageInterval(start_minute=480, end_minute=660),))

    def test_parse_several_hours_come_back_in_clock_order(self):
        payload = build_mirror(
            [
                off("2026-10-09T15:00:00+03:00", "2026-10-09T18:30:00+03:00"),
                off("2026-10-09T08:00:00+03:00", "2026-10-09T11:00:00+03:00"),
            ]
        )

        intervals = self.parse(payload)

        self.assertEqual(
            intervals,
            (OutageInterval(start_minute=480, end_minute=660), OutageInterval(start_minute=900, end_minute=1110)),
        )

    def test_parse_an_hour_running_to_midnight_ends_at_the_end_of_the_day(self):
        """The operator writes it as the next date, which the domain spells as minute 1440."""
        payload = build_mirror([off("2026-10-09T21:00:00+03:00", "2026-10-10T00:00:00+03:00")])

        intervals = self.parse(payload)

        self.assertEqual(intervals, (OutageInterval(start_minute=1260, end_minute=1440),))

    def test_parse_the_standing_weekly_grid_is_dropped_rather_than_shown(self):
        """«Preset» is what the group would be off on a Friday in general — it promises nothing about today."""
        payload = build_mirror([off("2026-10-09T08:00:00+03:00", "2026-10-09T11:00:00+03:00", origin="preset")])

        intervals = self.parse(payload)

        self.assertEqual(intervals, ())

    def test_parse_a_possible_hour_is_not_an_outage(self):
        payload = build_mirror([off("2026-10-09T08:00:00+03:00", "2026-10-09T11:00:00+03:00", kind="possible")])

        intervals = self.parse(payload)

        self.assertEqual(intervals, ())

    def test_parse_another_days_hours_are_left_for_that_day(self):
        payload = build_mirror([off("2026-10-09T08:00:00+03:00", "2026-10-09T11:00:00+03:00")])

        intervals = self.parse(payload, day=TOMORROW)

        self.assertEqual(intervals, ())

    def test_parse_a_mirror_that_has_frozen_is_refused(self):
        payload = build_mirror(
            [off("2026-10-09T08:00:00+03:00", "2026-10-09T11:00:00+03:00")], updated_at=published_hours_ago(31)
        )

        intervals = self.parse(payload)

        self.assertIsNone(intervals)

    def test_parse_a_mirror_reporting_its_own_poll_failed_is_refused(self):
        payload = build_mirror([off("2026-10-09T08:00:00+03:00", "2026-10-09T11:00:00+03:00")], ok=False)

        intervals = self.parse(payload)

        self.assertIsNone(intervals)

    def test_parse_a_payload_with_no_update_time_is_refused(self):
        payload = build_mirror([off("2026-10-09T08:00:00+03:00", "2026-10-09T11:00:00+03:00")])
        del payload["updatedAt"]

        intervals = self.parse(payload)

        self.assertIsNone(intervals)

    def test_parse_a_group_the_mirror_does_not_carry_is_refused(self):
        intervals = parse_group_intervals(build_mirror([]), "60.1", TODAY, KYIV, STALE_AFTER)

        self.assertIsNone(intervals)

    def test_parse_a_payload_without_schedules_is_refused(self):
        intervals = self.parse({"updatedAt": published_hours_ago(2), "status": {"ok": True}})

        self.assertIsNone(intervals)


class StubPublishedProvider:
    def __init__(self, outlook):
        self.outlook = outlook

    async def fetch(self):
        return self.outlook

    async def fetch_today(self):
        return self.outlook.today if self.outlook is not None else None


class StubOperatorTable:
    def __init__(self, intervals_by_day: dict):
        self.intervals_by_day = intervals_by_day
        self.asked_for: list[date] = []

    async def fetch_intervals(self, day):
        self.asked_for.append(day)
        return self.intervals_by_day.get(day)


def schedule(day: date, status: OutageScheduleStatus, intervals: tuple = ()) -> OutageSchedule:
    return OutageSchedule(
        day=day,
        status=status,
        off_intervals=intervals,
        updated_on=datetime(2026, 10, 9, 5, 22, tzinfo=timezone.utc),
    )


MORNING = (OutageInterval(start_minute=480, end_minute=660),)
EVENING = (OutageInterval(start_minute=900, end_minute=1110),)


class FilledOutageScheduleProviderTestCase(unittest.IsolatedAsyncioTestCase):
    """
    The hours the family asked to keep seeing during emergency shutdowns, without losing what Yasno says.

    yasno drops every hour the moment the regime turns, so the card had nothing on it but the banner — while
    the city's own app showed the operator's table all along.
    """

    async def test_fetch_an_empty_emergency_day_takes_the_operators_hours(self):
        provider = FilledOutageScheduleProvider(
            published=StubPublishedProvider(
                OutageOutlook(today=schedule(TODAY, OutageScheduleStatus.EMERGENCY_SHUTDOWNS), tomorrow=None)
            ),
            operator_table=StubOperatorTable({TODAY: MORNING}),
        )

        outlook = await provider.fetch()

        self.assertEqual(outlook.today.off_intervals, MORNING)

    async def test_fetch_filling_a_day_leaves_the_regime_exactly_as_yasno_published_it(self):
        """The banner is what tells the family these hours may not hold, so the status is never rewritten."""
        provider = FilledOutageScheduleProvider(
            published=StubPublishedProvider(
                OutageOutlook(today=schedule(TODAY, OutageScheduleStatus.EMERGENCY_SHUTDOWNS), tomorrow=None)
            ),
            operator_table=StubOperatorTable({TODAY: MORNING}),
        )

        outlook = await provider.fetch()

        self.assertEqual(outlook.today.status, OutageScheduleStatus.EMERGENCY_SHUTDOWNS)

    async def test_fetch_a_day_yasno_already_has_hours_for_is_left_untouched(self):
        operator_table = StubOperatorTable({TODAY: MORNING})
        provider = FilledOutageScheduleProvider(
            published=StubPublishedProvider(
                OutageOutlook(
                    today=schedule(TODAY, OutageScheduleStatus.SCHEDULE_APPLIES, EVENING),
                    tomorrow=None,
                )
            ),
            operator_table=operator_table,
        )

        outlook = await provider.fetch()

        self.assertEqual(outlook.today.off_intervals, EVENING)
        self.assertEqual(operator_table.asked_for, [])

    async def test_fetch_fills_tomorrow_as_well_when_the_operator_has_published_it(self):
        provider = FilledOutageScheduleProvider(
            published=StubPublishedProvider(
                OutageOutlook(
                    today=schedule(TODAY, OutageScheduleStatus.EMERGENCY_SHUTDOWNS),
                    tomorrow=schedule(TOMORROW, OutageScheduleStatus.EMERGENCY_SHUTDOWNS),
                )
            ),
            operator_table=StubOperatorTable({TODAY: MORNING, TOMORROW: EVENING}),
        )

        outlook = await provider.fetch()

        self.assertEqual(outlook.tomorrow.off_intervals, EVENING)

    async def test_fetch_a_day_the_operator_has_nothing_for_stays_empty(self):
        provider = FilledOutageScheduleProvider(
            published=StubPublishedProvider(
                OutageOutlook(today=schedule(TODAY, OutageScheduleStatus.EMERGENCY_SHUTDOWNS), tomorrow=None)
            ),
            operator_table=StubOperatorTable({}),
        )

        outlook = await provider.fetch()

        self.assertEqual(outlook.today.off_intervals, ())

    async def test_fetch_with_yasno_unreadable_yields_nothing_rather_than_hours_alone(self):
        """Without the regime there is no way to say whether the hours apply, so a card must not be built."""
        provider = FilledOutageScheduleProvider(
            published=StubPublishedProvider(None),
            operator_table=StubOperatorTable({TODAY: MORNING}),
        )

        outlook = await provider.fetch()

        self.assertIsNone(outlook)

    async def test_fetch_today_fills_the_single_day_the_forecast_asks_for(self):
        provider = FilledOutageScheduleProvider(
            published=StubPublishedProvider(
                OutageOutlook(today=schedule(TODAY, OutageScheduleStatus.EMERGENCY_SHUTDOWNS), tomorrow=None)
            ),
            operator_table=StubOperatorTable({TODAY: MORNING}),
        )

        today = await provider.fetch_today()

        self.assertEqual(today.off_intervals, MORNING)
