import random
import unittest
from datetime import date

from src.bot.handlers.newspaper.rendering import HalfPageRenderer
from src.modules.newspaper.crossword_layout import build_crossword
from src.modules.newspaper.domain import NewspaperIssue
from src.modules.newspaper.services.word_source import WordBank


class HalfPageRendererTestCase(unittest.TestCase):
    def test_render_an_issue_produces_a_single_page_pdf(self):
        crossword = build_crossword(random.Random(8).sample(WordBank().read_all(), 180), seed=8)
        issue = NewspaperIssue(id=1, number=1, week_starts_on=date(2026, 9, 14), crossword=crossword)

        document = HalfPageRenderer(title="").render(issue, date(2026, 9, 19))

        self.assertTrue(document.startswith(b"%PDF"))
        self.assertEqual(document.count(b"/Type /Page\n"), 1)
