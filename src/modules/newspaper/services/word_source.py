from pathlib import Path
from typing import Protocol

from src.modules.newspaper.domain import CrosswordClue, is_usable_clue, normalize_answer

WORD_BANK_PATH = Path(__file__).resolve().parent.parent / "crossword_words.tsv"


class WordSource(Protocol):
    """Somewhere a week's crossword words come from."""

    async def fetch_clues(self, excluded_answers: set[str]) -> list[CrosswordClue]:
        ...


class WordBank:
    """
    The checked list that ships with the code: every clue in it was written and verified by hand.

    it is the source the paper can always fall back on — no network, no quota, and no clue that was never read
    by a person before it was printed.
    """

    def __init__(self, path: Path = WORD_BANK_PATH):
        self.path = path

    async def fetch_clues(self, excluded_answers: set[str]) -> list[CrosswordClue]:
        return [clue for clue in self.read_all() if clue.answer not in excluded_answers]

    def read_all(self) -> list[CrosswordClue]:
        clues = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            answer, clue = line.split("\t")
            candidate = CrosswordClue(answer=normalize_answer(answer), clue=clue.strip())
            if is_usable_clue(candidate):
                clues.append(candidate)
        return clues
