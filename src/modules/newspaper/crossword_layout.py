"""Fitting words into a free-form crossword: every word crosses another, nothing touches that does not cross."""
import random
from dataclasses import dataclass, field

from src.modules.newspaper.domain import Crossword, CrosswordClue, CrosswordEntry

GRID_LIMIT = 15
TARGET_WORDS = 20
MINIMUM_WORDS = 12
ATTEMPTS = 12


@dataclass
class Placement:
    clue: CrosswordClue
    row: int
    column: int
    across: bool

    def cells(self) -> list[tuple[int, int]]:
        if self.across:
            return [(self.row, self.column + offset) for offset in range(len(self.clue.answer))]
        return [(self.row + offset, self.column) for offset in range(len(self.clue.answer))]


@dataclass
class Grid:
    letters: dict[tuple[int, int], str] = field(default_factory=dict)
    across_cells: set[tuple[int, int]] = field(default_factory=set)
    down_cells: set[tuple[int, int]] = field(default_factory=set)
    cells_by_letter: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    placements: list[Placement] = field(default_factory=list)
    top: int = 0
    bottom: int = 0
    left: int = 0
    right: int = 0

    def place(self, placement: Placement) -> None:
        cells = placement.cells()
        for cell, letter in zip(cells, placement.clue.answer, strict=True):
            if cell not in self.letters:
                self.letters[cell] = letter
                self.cells_by_letter.setdefault(letter, []).append(cell)
            (self.across_cells if placement.across else self.down_cells).add(cell)
        if not self.placements:
            self.top, self.left = cells[0]
            self.bottom, self.right = cells[-1]
        self.top = min(self.top, cells[0][0])
        self.left = min(self.left, cells[0][1])
        self.bottom = max(self.bottom, cells[-1][0])
        self.right = max(self.right, cells[-1][1])
        self.placements.append(placement)

    def count_crossings(self, placement: Placement) -> int | None:
        """How many letters a placement shares with the grid, or None when it cannot go there at all."""
        cells = placement.cells()
        first, last = cells[0], cells[-1]
        if placement.across:
            before, after = (first[0], first[1] - 1), (last[0], last[1] + 1)
            same_direction, sides = self.across_cells, ((-1, 0), (1, 0))
        else:
            before, after = (first[0] - 1, first[1]), (last[0] + 1, last[1])
            same_direction, sides = self.down_cells, ((0, -1), (0, 1))
        if before in self.letters or after in self.letters:
            return None
        if max(self.bottom, last[0]) - min(self.top, first[0]) >= GRID_LIMIT:
            return None
        if max(self.right, last[1]) - min(self.left, first[1]) >= GRID_LIMIT:
            return None

        crossings = 0
        for cell, letter in zip(cells, placement.clue.answer, strict=True):
            existing = self.letters.get(cell)
            if existing is not None:
                if existing != letter or cell in same_direction:
                    return None
                crossings += 1
                continue
            for row_step, column_step in sides:
                if (cell[0] + row_step, cell[1] + column_step) in self.letters:
                    return None
        return crossings

    def find_best_placement(self, clue: CrosswordClue) -> tuple[int, Placement] | None:
        best = None
        for index, letter in enumerate(clue.answer):
            for row, column in self.cells_by_letter.get(letter, []):
                for across in (True, False):
                    if across and (row, column) in self.across_cells:
                        continue
                    if not across and (row, column) in self.down_cells:
                        continue
                    placement = Placement(
                        clue=clue,
                        row=row if across else row - index,
                        column=column - index if across else column,
                        across=across,
                    )
                    crossings = self.count_crossings(placement)
                    if crossings and (best is None or crossings > best[0]):
                        best = (crossings, placement)
        return best


def build_crossword(candidates: list[CrosswordClue], seed: int) -> Crossword | None:
    """
    The densest grid a handful of shuffled attempts can find, or None when the words will not interlock.

    a free-form grid has no black squares to lean on, so density is what makes it a puzzle: a word that crosses
    two others can be half-guessed from them, a word that crosses one is a quiz question. longer words are laid
    first because they give the short ones something to hang from.
    """
    rng = random.Random(seed)
    best_grid = None
    for _ in range(ATTEMPTS):
        grid = _attempt(candidates, rng)
        if best_grid is None or _score(grid) > _score(best_grid):
            best_grid = grid
    if best_grid is None or len(best_grid.placements) < MINIMUM_WORDS:
        return None
    return _to_crossword(best_grid)


def _attempt(candidates: list[CrosswordClue], rng: random.Random) -> Grid:
    pool = list(candidates)
    rng.shuffle(pool)
    pool.sort(key=lambda clue: len(clue.answer), reverse=True)
    opener = pool.pop(rng.randrange(min(8, len(pool))))
    grid = Grid()
    grid.place(Placement(clue=opener, row=0, column=0, across=rng.random() < 0.5))

    while len(grid.placements) < TARGET_WORDS and pool:
        choice = None
        for index, clue in enumerate(pool):
            found = grid.find_best_placement(clue)
            if found is None:
                continue
            crossings, placement = found
            rank = (crossings, len(clue.answer), rng.random())
            if choice is None or rank > choice[0]:
                choice = (rank, index, placement)
        if choice is None:
            break
        _, index, placement = choice
        pool.pop(index)
        grid.place(placement)
    return grid


def _score(grid: Grid) -> tuple[int, int, int]:
    shared = sum(len(placement.clue.answer) for placement in grid.placements) - len(grid.letters)
    area = (grid.bottom - grid.top + 1) * (grid.right - grid.left + 1)
    return len(grid.placements), shared, -area


def _to_crossword(grid: Grid) -> Crossword:
    starts = sorted({(placement.row - grid.top, placement.column - grid.left) for placement in grid.placements})
    numbers = {start: number for number, start in enumerate(starts, start=1)}
    entries = [
        CrosswordEntry(
            number=numbers[(placement.row - grid.top, placement.column - grid.left)],
            answer=placement.clue.answer,
            clue=placement.clue.clue,
            across=placement.across,
            row=placement.row - grid.top,
            column=placement.column - grid.left,
        )
        for placement in grid.placements
    ]
    entries.sort(key=lambda entry: (entry.number, not entry.across))
    return Crossword(width=grid.right - grid.left + 1, height=grid.bottom - grid.top + 1, entries=entries)
