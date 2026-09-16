import asyncio
import random
from datetime import date, timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.newspaper.crossword_layout import build_crossword
from src.modules.newspaper.domain import (
    Crossword,
    CrosswordClue,
    CrosswordNotBuiltError,
    NewspaperIssue,
    is_usable_clue,
)
from src.modules.newspaper.services.word_source import WordSource

# half a year of issues before a word may return; at twenty words an issue that already takes most of the bank
RECENT_ISSUES_WITHOUT_REPEATS = 26
# ninety candidates still fill the grid, and a pool this small lets the first source's words — the fresh, harder
# ones — make up nearly half of it instead of being crowded out by the whole bank
CANDIDATE_POOL_SIZE = 90


class PrepareIssueUseCase(BaseUseCase):
    """
    This week's issue, ready to print — or None once it has been printed.

    the issue is saved before anything goes to the printer, so a retry an hour later prints the same crossword
    instead of drawing a new one, and the words it used stay out of the grids that follow.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar, word_sources: list[WordSource]):
        super().__init__(uow)
        self.household_calendar = household_calendar
        self.word_sources = word_sources

    async def __call__(self) -> NewspaperIssue | None:
        today = self.household_calendar.today()
        week_starts_on = today - timedelta(days=today.weekday())

        async with self.uow as uow:
            existing = await uow.newspaper_issues.retrieve_for_week(week_starts_on)
            if existing is not None:
                if existing.printed_at is not None:
                    return None
                return NewspaperIssue(
                    id=existing.id,
                    number=existing.number,
                    week_starts_on=existing.week_starts_on,
                    crossword=Crossword(**existing.crossword),
                )
            recent_answers = await uow.newspaper_issues.list_recent_answers(RECENT_ISSUES_WITHOUT_REPEATS)

        candidates = await self._gather_candidates(recent_answers, week_starts_on)
        # a second of pure cpu on a laptop and several on the pi — off the event loop, or the bot stops answering
        crossword = await asyncio.to_thread(build_crossword, candidates, _seed(week_starts_on))
        if crossword is None:
            raise CrosswordNotBuiltError(f"No crossword could be laid out for the week of {week_starts_on}")

        async with self.uow as uow:
            number = (await uow.newspaper_issues.retrieve_last_number() or 0) + 1
            saved = await uow.newspaper_issues.create(
                {"number": number, "week_starts_on": week_starts_on, "crossword": crossword.model_dump()}
            )
            return NewspaperIssue(id=saved.id, number=number, week_starts_on=week_starts_on, crossword=crossword)

    async def _gather_candidates(self, recent_answers: set[str], week_starts_on: date) -> list[CrosswordClue]:
        """Every source in order, the first to offer a word keeping its clue; the pool is then cut to size."""
        rng = random.Random(_seed(week_starts_on))
        seen: set[str] = set(recent_answers)
        preferred: list[CrosswordClue] = []
        for source in self.word_sources:
            offered = [clue for clue in await source.fetch_clues(recent_answers) if is_usable_clue(clue)]
            rng.shuffle(offered)
            for clue in offered:
                if clue.answer not in seen:
                    seen.add(clue.answer)
                    preferred.append(clue)
        return preferred[:CANDIDATE_POOL_SIZE]


def _seed(week_starts_on: date) -> int:
    return week_starts_on.toordinal()
