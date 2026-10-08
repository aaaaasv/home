import unittest
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from src.bot.handlers.power.formatting import render_outage_outlook
from src.modules.power.domain import OutageInterval, OutageOutlook, OutageSchedule, OutageScheduleStatus

KYIV = ZoneInfo("Europe/Kyiv")

EMERGENCY_BANNER = (
    "<blockquote>\U0001f6a8 <b>Аварійні відключення</b>\n"
    "Графік не діє — світло можуть вимкнути будь-коли й повернути без попередження.</blockquote>"
)


# 21:10 Kyiv on 7 october, which is when yasno really published that evening's hours
PUBLISHED = datetime(2026, 10, 7, 18, 10, tzinfo=timezone.utc)


def build_schedule(day: date, *intervals: OutageInterval, status=OutageScheduleStatus.SCHEDULE_APPLIES):
    return OutageSchedule(day=day, status=status, off_intervals=intervals, updated_on=PUBLISHED)


# the evening of 7 october 2026, as yasno actually published it at 21:10: two intervals today, one tomorrow
TODAY = build_schedule(date(2026, 10, 7), OutageInterval(0, 210), OutageInterval(1080, 1290))
TOMORROW = build_schedule(date(2026, 10, 8), OutageInterval(900, 1110))


class RenderOutageOutlookTestCase(unittest.TestCase):
    """The board answers «коли вимкнуть», so an hour that has finished is no longer part of the answer."""

    def test_render_ahead_of_both_days_lists_every_hour_and_names_each_day(self):
        """Read from the day before: nothing has been spent yet, and neither day is «сьогодні»."""
        rendered = render_outage_outlook(
            OutageOutlook(today=TODAY, tomorrow=TOMORROW), datetime(2026, 10, 6, 23, 0, tzinfo=KYIV)
        )

        self.assertEqual(
            rendered,
            "🗓 <b>Графік відключень</b>\n"
            "\n"
            "<b>Завтра</b>\n"
            "🕯 00:00–03:30\n"
            "🕯 18:00–21:30\n"
            "\n"
            "<b>8 жовтня</b>\n"
            "🕯 15:00–18:30\n"
            "\n"
            "<i>станом на 7 жовтня, 21:10</i>",
        )

    def test_render_drops_an_hour_that_has_already_finished(self):
        rendered = render_outage_outlook(
            OutageOutlook(today=TODAY, tomorrow=TOMORROW), datetime(2026, 10, 7, 9, 0, tzinfo=KYIV)
        )

        self.assertEqual(
            rendered,
            "🗓 <b>Графік відключень</b>\n"
            "\n"
            "<b>Сьогодні</b>\n"
            "🕯 18:00–21:30\n"
            "\n"
            "<b>Завтра</b>\n"
            "🕯 15:00–18:30\n"
            "\n"
            "<i>станом на 21:10</i>",
        )

    def test_render_inside_an_outage_marks_the_hour_that_is_running(self):
        rendered = render_outage_outlook(
            OutageOutlook(today=TODAY, tomorrow=TOMORROW), datetime(2026, 10, 7, 19, 0, tzinfo=KYIV)
        )

        self.assertIn("🕯 18:00–21:30 — зараз", rendered)
        self.assertNotIn("00:00–03:30", rendered)

    def test_render_once_the_day_is_spent_leaves_only_tomorrow(self):
        rendered = render_outage_outlook(
            OutageOutlook(today=TODAY, tomorrow=TOMORROW), datetime(2026, 10, 7, 23, 0, tzinfo=KYIV)
        )

        self.assertEqual(
            rendered,
            "🗓 <b>Графік відключень</b>\n" "\n" "<b>Завтра</b>\n" "🕯 15:00–18:30\n" "\n" "<i>станом на 21:10</i>",
        )

    def test_render_a_day_with_no_outages_leaves_its_heading_out(self):
        rendered = render_outage_outlook(
            OutageOutlook(today=build_schedule(date(2026, 10, 7)), tomorrow=TOMORROW),
            datetime(2026, 10, 7, 9, 0, tzinfo=KYIV),
        )

        self.assertNotIn("Сьогодні", rendered)
        self.assertIn("<b>Завтра</b>", rendered)

    def test_render_without_a_published_tomorrow_shows_today_alone(self):
        rendered = render_outage_outlook(
            OutageOutlook(today=TODAY, tomorrow=None), datetime(2026, 10, 7, 9, 0, tzinfo=KYIV)
        )

        self.assertEqual(
            rendered,
            "🗓 <b>Графік відключень</b>\n" "\n" "<b>Сьогодні</b>\n" "🕯 18:00–21:30\n" "\n" "<i>станом на 21:10</i>",
        )


class RenderEmergencyShutdownsTestCase(unittest.TestCase):
    """
    The banner stands beside the published hours, never instead of them.

    a day in emergency mode with no hours published used to be dropped from the board entirely, which took
    the board down at the one moment it had something to say.
    """

    def test_render_an_emergency_day_carries_the_banner_above_both_days(self):
        emergency = build_schedule(
            date(2026, 10, 7), OutageInterval(1080, 1290), status=OutageScheduleStatus.EMERGENCY_SHUTDOWNS
        )

        rendered = render_outage_outlook(
            OutageOutlook(today=emergency, tomorrow=TOMORROW), datetime(2026, 10, 7, 14, 0, tzinfo=KYIV)
        )

        self.assertEqual(
            rendered,
            "🗓 <b>Графік відключень</b>\n" + EMERGENCY_BANNER + "\n"
            "\n"
            "<b>Сьогодні</b>\n"
            "🕯 18:00–21:30\n"
            "\n"
            "<b>Завтра</b>\n"
            "🕯 15:00–18:30\n"
            "\n"
            "<i>станом на 21:10</i>",
        )

    def test_render_an_emergency_day_with_no_published_hours_still_shows_the_banner(self):
        emergency = build_schedule(date(2026, 10, 7), status=OutageScheduleStatus.EMERGENCY_SHUTDOWNS)

        rendered = render_outage_outlook(
            OutageOutlook(today=emergency, tomorrow=TOMORROW), datetime(2026, 10, 7, 14, 0, tzinfo=KYIV)
        )

        self.assertEqual(
            rendered,
            "🗓 <b>Графік відключень</b>\n" + EMERGENCY_BANNER + "\n"
            "\n"
            "<b>Завтра</b>\n"
            "🕯 15:00–18:30\n"
            "\n"
            "<i>станом на 21:10</i>",
        )

    def test_render_an_emergency_day_whose_hours_are_all_spent_keeps_the_banner(self):
        emergency = build_schedule(
            date(2026, 10, 7), OutageInterval(0, 210), status=OutageScheduleStatus.EMERGENCY_SHUTDOWNS
        )

        rendered = render_outage_outlook(
            OutageOutlook(today=emergency, tomorrow=None), datetime(2026, 10, 7, 14, 0, tzinfo=KYIV)
        )

        self.assertEqual(
            rendered,
            "🗓 <b>Графік відключень</b>\n" + EMERGENCY_BANNER + "\n" "\n" "<i>станом на 21:10</i>",
        )


if __name__ == "__main__":
    unittest.main()
