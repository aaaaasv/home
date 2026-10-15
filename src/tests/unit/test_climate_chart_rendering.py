import unittest
from datetime import date, timedelta

from src.bot.handlers.weather.chart import find_chart_font, render_climate_chart, smooth
from src.modules.weather.domain import ClimateDay, ClimateHistory

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def build_history(days: int = 30, indoor_from: int = 0) -> ClimateHistory:
    first = date(2026, 9, 15)
    outdoor = tuple(
        ClimateDay(
            day=first + timedelta(days=position),
            minimum_celsius=6.0 + position % 4,
            maximum_celsius=14.0 + position % 5,
            average_celsius=10.0 + position % 4,
            average_humidity_percent=70.0 + position % 10,
        )
        for position in range(days)
    )
    indoor = tuple(
        ClimateDay(
            day=first + timedelta(days=position),
            minimum_celsius=22.0,
            maximum_celsius=25.0 - position % 2,
            average_celsius=23.5,
            average_humidity_percent=45.0,
        )
        for position in range(indoor_from, days)
    )
    return ClimateHistory(indoor=indoor, outdoor=outdoor)


class RenderClimateChartTestCase(unittest.TestCase):
    """
    The picture itself: it has to come out of pillow alone, on whatever font the machine has.

    there is no font in the repository to fall back on — a truetype file is three quarters of a megabyte of
    binary — so where a machine has none the chart is not drawn at all, and these tests say so out loud.
    """

    def setUp(self):
        self.fonts = find_chart_font()
        if self.fonts is None:
            self.skipTest("no font on this machine; the image needs fonts-dejavu-core")

    def test_render_a_month_of_both_records_returns_a_png(self):
        picture = render_climate_chart(build_history(), self.fonts)

        self.assertEqual(picture[:8], PNG_MAGIC)

    def test_render_with_the_rooms_starting_later_than_the_sky_still_draws(self):
        """The sensors went in weeks after the weather log, and the chart must not wait for them."""
        picture = render_climate_chart(build_history(indoor_from=20), self.fonts)

        self.assertEqual(picture[:8], PNG_MAGIC)

    def test_render_with_the_sky_alone_draws_the_sky(self):
        history = ClimateHistory(outdoor=build_history().outdoor)

        picture = render_climate_chart(history, self.fonts)

        self.assertEqual(picture[:8], PNG_MAGIC)

    def test_render_with_a_single_day_on_each_side_draws_nothing(self):
        history = ClimateHistory(indoor=build_history(days=1).indoor, outdoor=build_history(days=1).outdoor)

        picture = render_climate_chart(history, self.fonts)

        self.assertIsNone(picture)

    def test_render_with_no_humidity_anywhere_still_draws_the_temperature(self):
        history = ClimateHistory(
            outdoor=tuple(day.model_copy(update={"average_humidity_percent": None}) for day in build_history().outdoor)
        )

        picture = render_climate_chart(history, self.fonts)

        self.assertEqual(picture[:8], PNG_MAGIC)


class SmoothTestCase(unittest.TestCase):
    """The weekly average is the line the eye reads, so it has to keep going all the way to today."""

    def test_smooth_over_a_flat_run_changes_nothing(self):
        self.assertEqual(smooth([5.0] * 10), [5.0] * 10)

    def test_smooth_reaches_the_last_day_rather_than_stopping_half_a_window_short(self):
        smoothed = smooth([0.0] * 6 + [7.0], window=7)

        self.assertEqual(len(smoothed), 7)
        self.assertAlmostEqual(smoothed[-1], 7.0 / 4)

    def test_smooth_flattens_one_odd_day(self):
        smoothed = smooth([10.0, 10.0, 10.0, 24.0, 10.0, 10.0, 10.0], window=7)

        self.assertAlmostEqual(smoothed[3], 12.0)
