from datetime import datetime, timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.model_budget.domain import ModelSpend

DAYS_IN_A_BILLING_MONTH = 30


class RetrieveModelSpendUseCase(BaseUseCase):
    """
    What the paid models have cost over the last day and the last month, against what they are allowed.

    the month is a rolling thirty days rather than a calendar one. the credits renew on their own date and
    the bot does not know it, and a rolling window is the safer of the two anyway: a calendar month lets a
    runaway loop spend everything on the 31st and start again free the next morning.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        household_calendar: HouseholdCalendar,
        daily_allowance_micro_usd: int,
        monthly_allowance_micro_usd: int,
    ):
        super().__init__(uow)
        self.household_calendar = household_calendar
        self.daily_allowance_micro_usd = daily_allowance_micro_usd
        self.monthly_allowance_micro_usd = monthly_allowance_micro_usd

    async def __call__(self) -> tuple[ModelSpend, ModelSpend]:
        """The day's spend and the month's, in that order."""
        now = self.household_calendar.now()
        async with self.uow as uow:
            day = await uow.model_usage.total_cost_since(self._start_of_day(now))
            month = await uow.model_usage.total_cost_since(now - timedelta(days=DAYS_IN_A_BILLING_MONTH))
        return (
            ModelSpend(spent_micro_usd=day, allowed_micro_usd=self.daily_allowance_micro_usd),
            ModelSpend(spent_micro_usd=month, allowed_micro_usd=self.monthly_allowance_micro_usd),
        )

    def _start_of_day(self, now: datetime) -> datetime:
        local = now.astimezone(self.household_calendar.timezone)
        return local.replace(hour=0, minute=0, second=0, microsecond=0)
