import unittest
from collections import Counter

from src.modules.newspaper.domain import CrosswordClue, is_usable_clue
from src.modules.newspaper.services.word_source import WORD_BANK_PATH, WordBank


class CrosswordWordBankTestCase(unittest.TestCase):
    """The bank is data, and a bad line in it is a broken puzzle on paper rather than an exception in a log."""

    def test_every_line_of_the_bank_is_a_word_the_grid_can_use(self):
        lines = [line for line in WORD_BANK_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]

        clues = WordBank().read_all()

        self.assertEqual(len(clues), len(lines))

    def test_no_answer_appears_twice_in_the_bank(self):
        clues = WordBank().read_all()

        repeated = [answer for answer, count in Counter(clue.answer for clue in clues).items() if count > 1]

        self.assertEqual(repeated, [])

    def test_the_bank_holds_enough_words_for_half_a_year_without_repeats(self):
        clues = WordBank().read_all()

        # twenty words an issue for twenty-six issues, with room left for the layout to choose from
        self.assertGreaterEqual(len(clues), 800)


class IsUsableClueTestCase(unittest.TestCase):
    def test_is_usable_clue_with_an_apostrophe_in_the_answer_is_refused(self):
        candidate = CrosswordClue(answer="М'ЯТА", clue="Запашна трава для чаю")

        usable = is_usable_clue(candidate)

        self.assertFalse(usable)

    def test_is_usable_clue_that_carries_the_start_of_its_answer_is_refused(self):
        candidate = CrosswordClue(answer="КОВАЛЬ", clue="Майстер біля ковадла")

        usable = is_usable_clue(candidate)

        self.assertFalse(usable)

    def test_is_usable_clue_with_a_three_letter_answer_is_refused(self):
        candidate = CrosswordClue(answer="ДУБ", clue="Дерево з жолудями")

        usable = is_usable_clue(candidate)

        self.assertFalse(usable)

    def test_is_usable_clue_with_a_plain_word_and_an_honest_clue_is_accepted(self):
        candidate = CrosswordClue(answer="ГОВЕРЛА", clue="Найвища вершина України")

        usable = is_usable_clue(candidate)

        self.assertTrue(usable)
