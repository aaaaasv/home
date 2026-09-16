import random
import unittest

from src.modules.newspaper.crossword_layout import GRID_LIMIT, MINIMUM_WORDS, build_crossword
from src.modules.newspaper.domain import CrosswordClue
from src.modules.newspaper.services.word_source import WordBank


def sample_bank(seed: int, size: int = 180) -> list[CrosswordClue]:
    return random.Random(seed).sample(WordBank().read_all(), size)


class BuildCrosswordTestCase(unittest.TestCase):
    """
    The layout has to be a real crossword on paper, which the eye checks and a test must check for it.

    a letter two words disagree on, or two words that touch without crossing, prints a puzzle that cannot be
    solved — and nobody finds out until saturday.
    """

    def test_build_crossword_from_the_bank_agrees_on_every_shared_letter(self):
        clues = sample_bank(seed=1)

        crossword = build_crossword(clues, seed=1)

        letters = {}
        for entry in crossword.entries:
            for cell, letter in zip(entry.cells(), entry.answer, strict=True):
                self.assertEqual(letters.setdefault(cell, letter), letter)

    def test_build_crossword_from_the_bank_never_lets_a_letter_touch_a_word_it_does_not_cross(self):
        clues = sample_bank(seed=2)

        crossword = build_crossword(clues, seed=2)

        owners = {}
        for index, entry in enumerate(crossword.entries):
            for cell in entry.cells():
                owners.setdefault(cell, set()).add(index)
        for (row, column), words in owners.items():
            for neighbour in ((row + 1, column), (row, column + 1)):
                if neighbour in owners:
                    self.assertTrue(words & owners[neighbour], f"{(row, column)} touches {neighbour} without a word")

    def test_build_crossword_from_the_bank_fits_the_half_page_grid_and_crosses_every_word(self):
        clues = sample_bank(seed=3)

        crossword = build_crossword(clues, seed=3)

        self.assertLessEqual(crossword.width, GRID_LIMIT)
        self.assertLessEqual(crossword.height, GRID_LIMIT)
        self.assertGreaterEqual(len(crossword.entries), MINIMUM_WORDS)
        shared = sum(len(entry.answer) for entry in crossword.entries) - len(crossword.letters())
        self.assertGreaterEqual(shared, len(crossword.entries) - 1)

    def test_build_crossword_numbers_the_starting_cells_in_reading_order(self):
        clues = sample_bank(seed=4)

        crossword = build_crossword(clues, seed=4)

        starts = sorted({(entry.row, entry.column) for entry in crossword.entries})
        self.assertEqual([crossword.numbers()[start] for start in starts], list(range(1, len(starts) + 1)))

    def test_build_crossword_with_the_same_words_and_seed_lays_out_the_same_grid(self):
        clues = sample_bank(seed=5)

        first, second = build_crossword(clues, seed=5), build_crossword(clues, seed=5)

        self.assertEqual(first, second)

    def test_build_crossword_from_words_that_share_no_letter_returns_none(self):
        clues = [CrosswordClue(answer=answer, clue="питання") for answer in ("АААА", "БББББ", "ВВВВ", "ГГГГГ")]

        crossword = build_crossword(clues, seed=6)

        self.assertIsNone(crossword)
