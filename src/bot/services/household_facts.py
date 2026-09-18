"""What the house knows about itself, gathered from every module for a question asked outside their topics."""
import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork


@dataclass(frozen=True)
class FactsContext:
    """What a module needs to read its own record — the facts counterpart of SchedulerContext."""

    household_calendar: HouseholdCalendar
    uow_factory: Callable[[], UnitOfWork]


FactsGatherer = Callable[[FactsContext], Awaitable[str]]


class HouseholdFacts:
    """
    Every module's own dossier behind one call, so the assistant topic knows what each module's topic knows.

    a question asked in «Запитати» is about this home, not about houseplants in general: «коли поливали Бубика»
    has an answer in the database, and without it the model can only say it does not know.
    """

    def __init__(self, gatherers: Sequence[FactsGatherer]):
        self.gatherers = gatherers

    async def gather(self, context: FactsContext) -> str:
        """The database and the calendar come from the update, the way every other handler dependency does."""
        dossiers = await asyncio.gather(*(gather_facts(context) for gather_facts in self.gatherers))
        return "\n\n".join(dossier for dossier in dossiers if dossier)
