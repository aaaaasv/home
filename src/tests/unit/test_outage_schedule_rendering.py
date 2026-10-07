import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.bot.handlers.power.formatting import render_outage_outlook
from src.modules.power.domain import OutageInterval, OutageOutlook, OutageSchedule, OutageScheduleStatus

KYIV = ZoneInfo("Europe/Kyiv")


def build_schedule(day: date, *intervals: OutageInterval, status=OutageScheduleStatus.SCHEDULE_APPLIES):
    return OutageSchedule(day=day, status=status, off_intervals=intervals, updated_on=None)


# the evening of 7 october 2026, as yasno actually published it at 21:10: two intervals today, one tomorrow
TODAY = build_schedule(date(2026, 10, 7), OutageInterval(0, 210), OutageInterval(1080, 1290))
TOMORROW = build_schedule(date(2026, 10, 8), OutageInterval(900, 1110))


class RenderOutageOutlookTestCase(unittest.TestCase):
    def test_render_at_an_hour_inside_an_outage_marks_the_spent_and_the_running_one(self):
        rendered = render_outage_outlook(
            OutageOutlook(today=TODAY, tomorrow=TOMORROW), datetime(2026, 10, 7, 21, 25, tzinfo=KYIV)
        )

        self.assertEqual(
            rendered,
            "🗓 <b>Графік відключень</b>\n"
            "\n"
            "<b>Сьогодні</b>\n"
            "🕯 <s>00:00–03:30</s>\n"
            "🕯 18:00–21:30 — зараз\n"
            "\n"
            "<b>Завтра</b>\n"
            "🕯 15:00–18:30\n"
            "\n"
            "<i>станом на 21:25</i>",
        )

    def test_render_before_any_outage_leaves_the_coming_hours_unmarked(self):
        rendered = render_outage_outlook(
            OutageOutlook(today=build_schedule(date(2026, 10, 7), OutageInterval(1080, 1290)), tomorrow=TOMORROW),
            datetime(2026, 10, 7, 9, 0, tzinfo=KYIV),
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
            "<i>станом на 09:00</i>",
        )

    def test_render_a_day_with_no_outages_leaves_its_heading_out(self):
        rendered = render_outage_outlook(
            OutageOutlook(today=build_schedule(date(2026, 10, 7)), tomorrow=TOMORROW),
            datetime(2026, 10, 7, 9, 0, tzinfo=KYIV),
        )

        self.assertEqual(
            rendered,
            "🗓 <b>Графік відключень</b>\n" "\n" "<b>Завтра</b>\n" "🕯 15:00–18:30\n" "\n" "<i>станом на 09:00</i>",
        )

    def test_render_without_a_published_tomorrow_shows_today_alone(self):
        rendered = render_outage_outlook(
            OutageOutlook(today=TODAY, tomorrow=None), datetime(2026, 10, 7, 9, 0, tzinfo=KYIV)
        )

        self.assertEqual(
            rendered,
            "🗓 <b>Графік відключень</b>\n"
            "\n"
            "<b>Сьогодні</b>\n"
            "🕯 <s>00:00–03:30</s>\n"
            "🕯 18:00–21:30\n"
            "\n"
            "<i>станом на 09:00</i>",
        )

    def test_render_an_emergency_day_carries_its_note_under_that_day(self):
        emergency = build_schedule(
            date(2026, 10, 7), OutageInterval(1080, 1290), status=OutageScheduleStatus.EMERGENCY_SHUTDOWNS
        )
        rendered = render_outage_outlook(
            OutageOutlook(today=emergency, tomorrow=TOMORROW), datetime(2026, 10, 7, 9, 0, tzinfo=KYIV)
        )

        self.assertEqual(
            rendered,
            "🗓 <b>Графік відключень</b>\n"
            "\n"
            "<b>Сьогодні</b>\n"
            "⚠️ аварійні відключення\n"
            "🕯 18:00–21:30\n"
            "\n"
            "<b>Завтра</b>\n"
            "🕯 15:00–18:30\n"
            "\n"
            "<i>станом на 09:00</i>",
        )

    def test_render_a_day_the_clock_has_left_behind_is_named_by_its_date(self):
        rendered = render_outage_outlook(
            OutageOutlook(today=TODAY, tomorrow=TOMORROW), datetime(2026, 10, 9, 9, 0, tzinfo=KYIV)
        )

        self.assertEqual(
            rendered,
            "🗓 <b>Графік відключень</b>\n"
            "\n"
            "<b>7 жовтня</b>\n"
            "🕯 00:00–03:30\n"
            "🕯 18:00–21:30\n"
            "\n"
            "<b>8 жовтня</b>\n"
            "🕯 15:00–18:30\n"
            "\n"
            "<i>станом на 09:00</i>",
        )


if __name__ == "__main__":
    unittest.main()
