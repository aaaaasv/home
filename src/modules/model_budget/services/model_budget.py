from collections.abc import Callable

from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.model_budget.services.usage_ledger import BudgetSpent
from src.modules.model_budget.use_cases.record_model_usage import RecordModelUsageUseCase
from src.modules.model_budget.use_cases.retrieve_model_spend import RetrieveModelSpendUseCase


class ModelBudget:
    """
    Two ceilings on what the paid models may cost: one for the day, one for the rolling month.

    the day is the one that matters. the month protects the credit; the day protects against the way it
    would actually be lost, which is a job that wakes every minute and asks the same question forever. the
    free tier used to be that guard by accident — it refused after twenty requests — and a key with credit
    behind it has no such floor.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        household_calendar: HouseholdCalendar,
        daily_allowance_micro_usd: int,
        monthly_allowance_micro_usd: int,
    ):
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar
        self.daily_allowance_micro_usd = daily_allowance_micro_usd
        self.monthly_allowance_micro_usd = monthly_allowance_micro_usd

    async def refuse_if_spent(self) -> None:
        day, month = await self._retrieve_spend()
        if day.is_spent:
            raise BudgetSpent(is_daily=True)
        if month.is_spent:
            raise BudgetSpent(is_daily=False)

    async def record(self, purpose: str, model: str, input_tokens: int, output_tokens: int) -> None:
        await RecordModelUsageUseCase(uow=self.uow_factory(), household_calendar=self.household_calendar)(
            purpose=purpose, model=model, input_tokens=input_tokens, output_tokens=output_tokens
        )

    async def _retrieve_spend(self):
        return await RetrieveModelSpendUseCase(
            uow=self.uow_factory(),
            household_calendar=self.household_calendar,
            daily_allowance_micro_usd=self.daily_allowance_micro_usd,
            monthly_allowance_micro_usd=self.monthly_allowance_micro_usd,
        )()
