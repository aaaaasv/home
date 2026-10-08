from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.model_budget.services.price_list import price_of


class RecordModelUsageUseCase(BaseUseCase):
    """One paid call, priced and written down the moment it returns."""

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, purpose: str, model: str, input_tokens: int, output_tokens: int) -> int:
        cost = price_of(model, input_tokens, output_tokens)
        async with self.uow as uow:
            await uow.model_usage.create(
                {
                    "purpose": purpose,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_micro_usd": cost,
                    "at": self.household_calendar.now(),
                }
            )
        return cost
