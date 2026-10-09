from datetime import timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import GridState


class RecordGridChangeUseCase(BaseUseCase):
    """
    Writes down that the grid changed, and answers how long the state before it lasted.

    the span is the half of the message the family actually talks about — «світло є» says the waiting is over,
    «не було 2 год 26 хв» says how bad it was. it can only be computed here, because the process restarts on
    every deploy and the previous change may have been announced by a process that no longer exists.

    the row is written whether or not a span can be worked out, so the record stays complete even when it is
    the first change this house ever saw.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, grid: GridState) -> timedelta | None:
        now = self.household_calendar.now()
        async with self.uow as uow:
            previous = await uow.grid_events.retrieve_latest()
            await uow.grid_events.create({"state": grid.value, "at": now})
        if previous is None or previous.state == grid.value:
            return None
        return now - previous.at
