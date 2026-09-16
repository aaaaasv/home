from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork


class MarkIssuePrintedUseCase(BaseUseCase):
    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, issue_id: int) -> None:
        async with self.uow as uow:
            await uow.newspaper_issues.mark_printed(issue_id, self.household_calendar.now())
