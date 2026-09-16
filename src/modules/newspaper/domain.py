import re
from datetime import date

from src.common.domain import DomainModel
from src.common.exceptions import DomainError

UKRAINIAN_LETTERS = re.compile(r"^[АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ]+$")
SHORTEST_ANSWER = 4
LONGEST_ANSWER = 13
LONGEST_CLUE = 80


class CrosswordNotBuiltError(DomainError):
    pass


class CrosswordClue(DomainModel):
    """A word the grid may use, and what the solver is told about it."""

    answer: str
    clue: str


class CrosswordEntry(DomainModel):
    number: int
    answer: str
    clue: str
    across: bool
    row: int
    column: int

    def cells(self) -> list[tuple[int, int]]:
        if self.across:
            return [(self.row, self.column + offset) for offset in range(len(self.answer))]
        return [(self.row + offset, self.column) for offset in range(len(self.answer))]


class Crossword(DomainModel):
    width: int
    height: int
    entries: list[CrosswordEntry]

    def letters(self) -> dict[tuple[int, int], str]:
        return {
            cell: letter for entry in self.entries for cell, letter in zip(entry.cells(), entry.answer, strict=True)
        }

    def numbers(self) -> dict[tuple[int, int], int]:
        return {(entry.row, entry.column): entry.number for entry in self.entries}

    def across(self) -> list[CrosswordEntry]:
        return [entry for entry in self.entries if entry.across]

    def down(self) -> list[CrosswordEntry]:
        return [entry for entry in self.entries if not entry.across]


class NewspaperIssue(DomainModel):
    id: int
    number: int
    week_starts_on: date
    crossword: Crossword


def normalize_answer(word: str) -> str:
    return word.strip().upper()


def is_usable_clue(candidate: CrosswordClue) -> bool:
    """
    Whether a word can go into the grid as it stands.

    one letter per cell, so an apostrophe, a hyphen or a space rules a word out. a clue that carries the start of
    its own answer gives it away, and one too long for a line breaks the half-page layout.
    """
    answer = candidate.answer
    if not UKRAINIAN_LETTERS.match(answer) or not SHORTEST_ANSWER <= len(answer) <= LONGEST_ANSWER:
        return False
    clue = candidate.clue.strip()
    if not clue or len(clue) > LONGEST_CLUE:
        return False
    stem = answer[: max(SHORTEST_ANSWER, len(answer) - 2)].lower()
    return stem not in clue.lower()
