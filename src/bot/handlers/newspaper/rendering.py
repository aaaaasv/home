"""The half-page issue as a pdf, laid out for the top half of an A4 sheet."""
from datetime import date
from pathlib import Path

from fpdf import FPDF

from src.bot.formatting import GENITIVE_MONTH_NAMES
from src.bot.handlers.newspaper import messages
from src.modules.newspaper.domain import Crossword, NewspaperIssue

FONTS = Path(__file__).resolve().parent / "fonts"
PAGE_WIDTH = 210.0
HALF_PAGE_HEIGHT = 148.5
MARGIN_SIDE = 11.0
MARGIN_TOP = 9.0
CELL_SIZE = 6.3
CLUES_WIDTH = 86.0
# the page is printed every week for years, so it spends ink only where a solver needs it. measured on the 360 dpi
# raster the driver sends: 1216 mm² of black per half page with a regular face and 0.12 mm rules, 582 mm² with this
TYPEFACE = "FiraSansCondensed-ExtraLight.ttf"
# ghostscript fills every pixel a path touches, so a rule thinner than one dot still prints as exactly one dot — the
# thinnest line the printer can make — while 0.12 mm came out two or three dots wide
GRID_LINE_WIDTH = 0.02
# the cell outline dashed rather than solid still reads as a cell, at half the ink
GRID_DASH = 0.45
# each stripe is taller than one ink's 180-nozzle column (about 25 mm), so a single pass fires every nozzle of
# every ink: solid black, cyan, magenta and yellow, and two pale tints the printer lays with its light inks.
# height is what reaches every nozzle; width only spends ink, so the stripes are as narrow as a clean line allows
INK_STRIPES = (
    ("K", (0, 0, 0)),
    ("C", (0, 255, 255)),
    ("M", (255, 0, 255)),
    ("Y", (255, 255, 0)),
    ("lc", (200, 255, 255)),
    ("lm", (255, 200, 255)),
)
STRIPE_WIDTH = 1.5
STRIPE_GAP = 1.0
STRIPE_HEIGHT = 30.0


class HalfPageRenderer:
    """
    Keeps the ink to what a week needs: one-dot dashed cells, an extra-light face, and six narrow stripes as the colour.

    everything sits in the top half of the page, so the same sheet takes four issues — two halves, two sides —
    by being turned before it goes back into the tray.
    """

    def __init__(self, title: str):
        self.title = title or messages.DEFAULT_TITLE

    def render(self, issue: NewspaperIssue, printed_on: date) -> bytes:
        pdf = FPDF(orientation="portrait", unit="mm", format="A4")
        pdf.set_auto_page_break(False)
        pdf.set_margins(0, 0, 0)
        pdf.add_font("sans", "", str(FONTS / TYPEFACE))
        pdf.add_page()
        pdf.set_draw_color(0, 0, 0)
        pdf.set_text_color(0, 0, 0)

        grid_top = self._draw_masthead(pdf, issue, printed_on)
        self._draw_grid(pdf, issue.crossword, grid_top)
        clues_left = PAGE_WIDTH - MARGIN_SIDE - CLUES_WIDTH
        self._draw_clues(pdf, issue.crossword, clues_left, grid_top)
        self._draw_footer(pdf, issue.crossword, clues_left)
        return bytes(pdf.output())

    def _draw_masthead(self, pdf: FPDF, issue: NewspaperIssue, printed_on: date) -> float:
        pdf.set_font("sans", "", 19)
        pdf.set_xy(MARGIN_SIDE, MARGIN_TOP)
        pdf.cell(0, 9, self.title.upper())
        issue_line = messages.ISSUE_LINE.format(
            number=issue.number,
            weekday=messages.WEEKDAY_NAMES[printed_on.weekday()],
            day=f"{printed_on.day} {GENITIVE_MONTH_NAMES[printed_on.month - 1]} {printed_on.year}",
        )
        pdf.set_font("sans", "", 8.5)
        pdf.set_xy(MARGIN_SIDE, MARGIN_TOP + 2.5)
        pdf.cell(PAGE_WIDTH - 2 * MARGIN_SIDE, 6, issue_line, align="R")
        return MARGIN_TOP + 15.5

    def _draw_grid(self, pdf: FPDF, crossword: Crossword, top: float) -> None:
        # each edge once: two neighbouring cells share one, and a dash drawn twice drifts out of step with itself
        edges = set()
        for row, column in crossword.letters():
            edges.update({(row, column, True), (row + 1, column, True), (row, column, False), (row, column + 1, False)})
        pdf.set_line_width(GRID_LINE_WIDTH)
        pdf.set_dash_pattern(dash=GRID_DASH, gap=GRID_DASH)
        for row, column, horizontal in sorted(edges):
            x, y = MARGIN_SIDE + column * CELL_SIZE, top + row * CELL_SIZE
            if horizontal:
                pdf.line(x, y, x + CELL_SIZE, y)
            else:
                pdf.line(x, y, x, y + CELL_SIZE)
        pdf.set_dash_pattern()

        pdf.set_font("sans", "", 5)
        for (row, column), number in crossword.numbers().items():
            pdf.set_xy(MARGIN_SIDE + column * CELL_SIZE + 0.4, top + row * CELL_SIZE + 0.45)
            pdf.cell(3, 1.8, str(number))

    def _draw_clues(self, pdf: FPDF, crossword: Crossword, left: float, top: float) -> None:
        pdf.set_xy(left, top - 1)
        for heading, entries in (
            (messages.ACROSS_HEADING, crossword.across()),
            (messages.DOWN_HEADING, crossword.down()),
        ):
            pdf.set_x(left)
            pdf.set_font("sans", "", 8)
            pdf.cell(CLUES_WIDTH, 4.4, heading.upper(), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("sans", "", 7.8)
            for entry in sorted(entries, key=lambda item: item.number):
                pdf.set_x(left)
                pdf.multi_cell(
                    CLUES_WIDTH,
                    3.5,
                    f"{entry.number}. {entry.clue} ({len(entry.answer)})",
                    new_x="LMARGIN",
                    new_y="NEXT",
                )
            pdf.set_y(pdf.get_y() + 1.4)

    def _draw_footer(self, pdf: FPDF, crossword: Crossword, clues_left: float) -> None:
        bottom = HALF_PAGE_HEIGHT - 8
        stripes_width = len(INK_STRIPES) * (STRIPE_WIDTH + STRIPE_GAP) - STRIPE_GAP
        stripes_left = PAGE_WIDTH - MARGIN_SIDE - stripes_width
        stripes_top = bottom - STRIPE_HEIGHT - 2.5
        pdf.set_font("sans", "", 5)
        for index, (label, colour) in enumerate(INK_STRIPES):
            x = stripes_left + index * (STRIPE_WIDTH + STRIPE_GAP)
            pdf.set_fill_color(*colour)
            pdf.rect(x, stripes_top, STRIPE_WIDTH, STRIPE_HEIGHT, style="F")
            pdf.set_xy(x - 1, stripes_top + STRIPE_HEIGHT + 0.4)
            pdf.cell(STRIPE_WIDTH + 2, 2, label, align="C")

        answers = " · ".join(
            f"{entry.number}{messages.ACROSS_MARK if entry.across else messages.DOWN_MARK} {entry.answer.capitalize()}"
            for entry in sorted(crossword.entries, key=lambda item: (item.number, not item.across))
        )
        answers_width = stripes_left - clues_left - 4
        pdf.set_font("sans", "", 5.2)
        text = f"{messages.ANSWERS_LABEL}: {answers}"
        lines = pdf.multi_cell(answers_width, 2.3, text, dry_run=True, output="LINES")
        block_height = len(lines) * 2.3
        # upside down, the way a newspaper hides its answers from a solver who is still solving
        with pdf.rotation(180, x=clues_left + answers_width / 2, y=bottom - block_height / 2):
            pdf.set_xy(clues_left, bottom - block_height)
            pdf.multi_cell(answers_width, 2.3, text)
