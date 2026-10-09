import unittest
from datetime import timedelta

from src.bot.handlers.power.formatting import format_span, render_mains_change
from src.modules.power.domain import GridState


class FormatSpanTestCase(unittest.TestCase):
    """
    A stretch of time as the family would say it out loud.

    the light is routinely on for days between outages, so this cannot be the station's runtime formatter —
    that one would answer «76 год 15 хв», which nobody reads as three days.
    """

    def test_format_a_span_under_an_hour_is_minutes_alone(self):
        self.assertEqual(format_span(timedelta(minutes=35)), "35 хв")

    def test_format_a_span_of_whole_hours_leaves_the_minutes_off(self):
        self.assertEqual(format_span(timedelta(hours=5)), "5 год")

    def test_format_a_span_of_hours_and_minutes_carries_both(self):
        self.assertEqual(format_span(timedelta(hours=2, minutes=26)), "2 год 26 хв")

    def test_format_a_span_of_one_day_says_den(self):
        self.assertEqual(format_span(timedelta(days=1, hours=4)), "1 день 4 год")

    def test_format_a_span_of_two_days_says_dni(self):
        self.assertEqual(format_span(timedelta(days=2, hours=3)), "2 дні 3 год")

    def test_format_a_span_of_five_days_says_dniv(self):
        self.assertEqual(format_span(timedelta(days=5)), "5 днів")

    def test_format_a_span_of_eleven_days_says_dniv_because_the_teens_all_do(self):
        self.assertEqual(format_span(timedelta(days=11)), "11 днів")

    def test_format_a_span_of_twenty_one_days_says_den_again(self):
        self.assertEqual(format_span(timedelta(days=21)), "21 день")

    def test_format_a_whole_number_of_days_leaves_the_hours_off(self):
        self.assertEqual(format_span(timedelta(days=3)), "3 дні")

    def test_format_a_span_shorter_than_a_minute_is_said_in_words(self):
        """The hat logged two of these on 7 october: gone and back inside the same second."""
        self.assertEqual(format_span(timedelta(seconds=20)), "менше хвилини")


class RenderMainsChangeWithSpanTestCase(unittest.TestCase):
    """
    How long it has been is the one thing nobody can look up afterwards.

    by the time anyone opens a board the outage is over, so if this message does not carry the span it is
    gone — and «скільки не було?» is the first thing anybody asks.
    """

    def test_render_the_grid_returning_says_how_long_there_was_none(self):
        text = render_mains_change(GridState.ON_GRID, timedelta(hours=2, minutes=26))

        self.assertEqual(text, "💡 <b>Світло є</b> (не було 2 год 26 хв)")

    def test_render_the_grid_going_says_how_long_there_was_light(self):
        text = render_mains_change(GridState.ON_BATTERY, timedelta(hours=5, minutes=20))

        self.assertEqual(text, "🕯 <b>Світло зникло</b> (було 5 год 20 хв)")

    def test_render_without_a_known_span_says_the_fact_alone(self):
        """The very first change this house ever recorded has nothing before it to measure against."""
        self.assertEqual(render_mains_change(GridState.ON_GRID), "💡 <b>Світло є</b>")
        self.assertEqual(render_mains_change(GridState.ON_BATTERY), "🕯 <b>Світло зникло</b>")
