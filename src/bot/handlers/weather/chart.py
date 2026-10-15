"""The month of air as a picture: the rooms and the sky, temperature over humidity.

Drawn with Pillow, which the bot already carries for the plant photos — a chart library would be sixty
megabytes on an arm64 image for four lines and two shaded bands. The one thing the image needs that the
container does not have by default is a font, so the composition root looks for one and simply does not
build the chart where there is none.
"""
import logging
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.bot.formatting import GENITIVE_MONTH_NAMES
from src.bot.handlers.weather.messages import (
    WEATHER_CHART_DEGREES,
    WEATHER_CHART_DRIFT_PART,
    WEATHER_CHART_FOOTNOTE,
    WEATHER_CHART_HUMIDITY,
    WEATHER_CHART_INDOOR,
    WEATHER_CHART_INDOOR_FOOTNOTE,
    WEATHER_CHART_OUTDOOR,
    WEATHER_CHART_PERCENT,
    WEATHER_CHART_SUBTITLE,
    WEATHER_CHART_SUBTITLE_WITH_DRIFT,
    WEATHER_CHART_TEMPERATURE,
    WEATHER_CHART_TITLE,
)
from src.modules.weather.domain import ClimateDay, ClimateHistory

logger = logging.getLogger(__name__)

# the debian package is fonts-dejavu-core; the rest are where a mac keeps something with cyrillic in it,
# so the same code draws the same picture on a laptop while a chart is being designed
FONT_CANDIDATES = (
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
)

# drawn at three times the size and shrunk back, because pillow has no anti-aliasing of its own and a
# one-pixel line on a phone screen looks like a dotted one
SCALE = 3
WIDTH, HEIGHT = 1000, 780
LEFT, RIGHT, TOP, BOTTOM = 86, 150, 118, 86
TEMPERATURE_FLOOR = 410
HUMIDITY_CEILING = 510

CARD = (252, 251, 249)
INK = (34, 33, 38)
MUTED = (132, 130, 140)
GRID = (231, 229, 234)
OUTDOOR = (58, 124, 196)
OUTDOOR_PALE = (160, 196, 232)
OUTDOOR_BAND = (58, 124, 196, 46)
INDOOR = (221, 126, 44)
INDOOR_PALE = (240, 196, 150)
INDOOR_BAND = (221, 126, 44, 46)

# a week, centred: long enough to swallow one sunny afternoon, short enough to turn when the season does
TREND_WINDOW = 7


def find_chart_font() -> tuple[Path, Path] | None:
    """The first font pair that is actually on this machine, or None — in which case nothing is drawn."""
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            return Path(regular), Path(bold)
    return None


def smooth(values: list[float], window: int = TREND_WINDOW) -> list[float]:
    """
    A centred average over the window, and at the ends over whatever part of it exists.

    the alternative is to stop the line half a window short of today, which hides the end everybody looks
    at first. the last points move a little as the days fill in, and that is the honest cost.
    """
    smoothed = []
    for position in range(len(values)):
        piece = values[max(0, position - window // 2) : position + window // 2 + 1]
        smoothed.append(sum(piece) / len(piece))
    return smoothed


def render_climate_chart(history: ClimateHistory, fonts: tuple[Path, Path]) -> bytes | None:
    """The whole picture as png bytes, or None when there is not enough of a record to draw a line."""
    if len(history.outdoor) < 2 and len(history.indoor) < 2:
        return None
    return _Chart(history, fonts).draw()


class _Chart:
    def __init__(self, history: ClimateHistory, fonts: tuple[Path, Path]):
        self.history = history
        self.regular, self.bold = fonts
        self.image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), CARD)
        self.pen = ImageDraw.Draw(self.image, "RGBA")
        every_day = [day.day for day in history.indoor + history.outdoor]
        self.first_day, self.last_day = min(every_day), max(every_day)

    # ── the page ────────────────────────────────────────────────────────────
    def draw(self) -> bytes:
        self._header()
        self._legend()
        self._temperature()
        self._humidity()
        self._footnote()
        canvas = BytesIO()
        self.image.resize((WIDTH, HEIGHT), Image.LANCZOS).save(canvas, format="PNG", optimize=True)
        return canvas.getvalue()

    def _header(self) -> None:
        self._text((LEFT - 18, 34), WEATHER_CHART_TITLE, 26, bold=True)
        self._text((LEFT - 18, 68), self._subtitle(), 15, fill=MUTED)

    def _subtitle(self) -> str:
        stamp = {"first": _spoken(self.first_day), "last": _spoken(self.last_day)}
        drift = " · ".join(
            WEATHER_CHART_DRIFT_PART.format(name=name, change=change)
            for name, change in (
                (WEATHER_CHART_OUTDOOR, _week_on_week(self.history.outdoor)),
                (WEATHER_CHART_INDOOR, _week_on_week(self.history.indoor)),
            )
            if change is not None
        )
        if not drift:
            return WEATHER_CHART_SUBTITLE.format(**stamp)
        return WEATHER_CHART_SUBTITLE_WITH_DRIFT.format(drift=drift, **stamp)

    def _legend(self) -> None:
        right = WIDTH - RIGHT - 10
        for caption, colour in ((WEATHER_CHART_OUTDOOR, OUTDOOR), (WEATHER_CHART_INDOOR, INDOOR)):
            width = self.pen.textlength(caption, font=self._font(14)) / SCALE
            self._text((right, 72), caption, 14, fill=colour, anchor="ra")
            swatch = right - width - 16
            self.pen.rectangle([(swatch * SCALE, 76 * SCALE), ((swatch + 10) * SCALE, 82 * SCALE)], fill=colour)
            right = swatch - 26

    def _footnote(self) -> None:
        note = WEATHER_CHART_FOOTNOTE
        if self.history.indoor:
            note = f"{note} · {WEATHER_CHART_INDOOR_FOOTNOTE}"
        self._text((LEFT - 18, HEIGHT - 26), note, 13, fill=MUTED)

    # ── the two panels ──────────────────────────────────────────────────────
    def _temperature(self) -> None:
        readings = [
            value
            for series in (self.history.indoor, self.history.outdoor)
            for day in series
            for value in (day.minimum_celsius, day.maximum_celsius)
        ]
        panel = _Panel(self, min(readings) - 1.5, max(readings) + 1.5, TOP, TEMPERATURE_FLOOR)
        self._panel_label(WEATHER_CHART_TEMPERATURE, TOP)
        panel.grid(5, WEATHER_CHART_DEGREES)
        for series, line, pale, band in (
            (self.history.outdoor, OUTDOOR, OUTDOOR_PALE, OUTDOOR_BAND),
            (self.history.indoor, INDOOR, INDOOR_PALE, INDOOR_BAND),
        ):
            if not series:
                continue
            panel.band(series, band)
            values = [day.average_celsius for day in series]
            panel.line(series, values, pale, 2)
            panel.line(series, smooth(values), line, 4)
            panel.mark(series[-1].day, values[-1], line, WEATHER_CHART_DEGREES.format(value=values[-1]))

    def _humidity(self) -> None:
        series = {
            name: [day for day in days if day.average_humidity_percent is not None]
            for name, days in (("outdoor", self.history.outdoor), ("indoor", self.history.indoor))
        }
        readings = [day.average_humidity_percent for days in series.values() for day in days]
        if not readings:
            # no humidity anywhere is a flat without sensors, which is a chart about temperature alone
            _Panel(self, 0, 1, HUMIDITY_CEILING, HEIGHT - BOTTOM).dates()
            return

        panel = _Panel(self, min(readings) - 6, max(readings) + 6, HUMIDITY_CEILING, HEIGHT - BOTTOM)
        panel.grid(20, WEATHER_CHART_PERCENT)
        panel.dates()
        self._panel_label(WEATHER_CHART_HUMIDITY, HUMIDITY_CEILING)
        for name, line, pale in (("outdoor", OUTDOOR, OUTDOOR_PALE), ("indoor", INDOOR, INDOOR_PALE)):
            days = series[name]
            if not days:
                continue
            values = [day.average_humidity_percent for day in days]
            panel.line(days, values, pale, 2)
            panel.line(days, smooth(values), line, 4)
            panel.mark(days[-1].day, values[-1], line, WEATHER_CHART_PERCENT.format(value=values[-1]))

    # ── the pen ─────────────────────────────────────────────────────────────
    def _font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(self.bold if bold else self.regular), size * SCALE)

    def _panel_label(self, caption: str, panel_top: float) -> None:
        """Which of the two this panel is. The axis says ° or %, but a title alone left people guessing."""
        self._text((LEFT - 18, panel_top - 26), caption, 12, bold=True, fill=MUTED)

    def _text(self, position, value, size=15, bold=False, fill=INK, anchor="la") -> None:
        self.pen.text(
            (position[0] * SCALE, position[1] * SCALE), value, font=self._font(size, bold), fill=fill, anchor=anchor
        )

    def _stroke(self, points, fill, width) -> None:
        self.pen.line([(x * SCALE, y * SCALE) for x, y in points], fill=fill, width=width * SCALE, joint="curve")


class _Panel:
    """One pair of axes: days across, one unit up the side."""

    def __init__(self, chart: _Chart, low: float, high: float, top: float, bottom: float):
        self.chart = chart
        self.low, self.high = low, high
        self.top, self.bottom = top, bottom

    def x(self, day: date) -> float:
        span = (self.chart.last_day - self.chart.first_day).days or 1
        return LEFT + (day - self.chart.first_day).days / span * (WIDTH - RIGHT - LEFT)

    def y(self, value: float) -> float:
        span = self.high - self.low or 1
        return self.bottom - (value - self.low) / span * (self.bottom - self.top)

    def grid(self, step: float, template: str) -> None:
        level = self.low - self.low % step
        while level <= self.high:
            if level >= self.low:
                self.chart._stroke([(LEFT - 10, self.y(level)), (WIDTH - RIGHT + 10, self.y(level))], GRID, 1)
                self.chart._text((LEFT - 18, self.y(level)), template.format(value=level), 14, fill=MUTED, anchor="rm")
            level += step

    def dates(self, every: int = 5) -> None:
        """Every fifth day, and always the last one — the right edge is the day anybody checks first."""
        span = (self.chart.last_day - self.chart.first_day).days
        offsets = sorted({*range(0, span + 1, every), span})
        # two labels on top of each other where the last tick nearly lands on the end
        if len(offsets) > 1 and offsets[-1] - offsets[-2] < every / 2:
            offsets.pop(-2)
        for offset in offsets:
            day = self.chart.first_day + timedelta(days=offset)
            self.chart._text((self.x(day), self.bottom + 14), f"{day:%d.%m}", 13, fill=MUTED, anchor="ma")

    def band(self, series: tuple[ClimateDay, ...], fill) -> None:
        upper = [(self.x(day.day), self.y(day.maximum_celsius)) for day in series]
        lower = [(self.x(day.day), self.y(day.minimum_celsius)) for day in reversed(series)]
        self.chart.pen.polygon([(x * SCALE, y * SCALE) for x, y in upper + lower], fill=fill)

    def line(self, series, values: list[float], colour, width: int) -> None:
        self.chart._stroke([(self.x(day.day), self.y(value)) for day, value in zip(series, values)], colour, width)

    def mark(self, day: date, value: float, colour, caption: str) -> None:
        x, y = self.x(day), self.y(value)
        self.chart.pen.ellipse([((x - 4) * SCALE, (y - 4) * SCALE), ((x + 4) * SCALE, (y + 4) * SCALE)], fill=colour)
        self.chart._text((x + 14, y - 11), caption, 17, bold=True, fill=colour)


def _spoken(day: date) -> str:
    return f"{day.day} {GENITIVE_MONTH_NAMES[day.month - 1]}"


def _week_on_week(series: tuple[ClimateDay, ...]) -> float | None:
    """
    How far the thick line has moved in a week — the number has to agree with the picture beside it.

    week against week was the obvious reading and it disagreed: a fortnight whose cold all arrived in the
    last three days averages out to «+0.0°» while the line on the chart visibly dives.
    """
    if len(series) <= TREND_WINDOW:
        return None
    trend = smooth([day.average_celsius for day in series])
    return trend[-1] - trend[-1 - TREND_WINDOW]
