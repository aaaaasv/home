from datetime import timedelta

from src.infrastructure.db.uow import UnitOfWork
from src.modules.model_budget.services.model_budget import ModelBudget
from src.modules.model_budget.services.usage_ledger import BudgetSpent
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase

A_DOLLAR = 1_000_000
OPUS = "claude-opus-5-5"


class ModelBudgetTestCase(BaseIntegrationTestCase):
    """
    The guard the free tier used to be by accident.

    gemini refused after twenty requests a day, so the worst a runaway job could do was go quiet. a key with
    credit behind it has no such floor, and an in-memory counter is reset by the very crash loop it exists to
    catch — hence a table.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_budget(self, daily_usd: float = 1.0, monthly_usd: float = 10.0) -> ModelBudget:
        return ModelBudget(
            uow_factory=self.uow_factory,
            household_calendar=self.household_calendar,
            daily_allowance_micro_usd=round(daily_usd * A_DOLLAR),
            monthly_allowance_micro_usd=round(monthly_usd * A_DOLLAR),
        )

    async def seed_usage(self, cost_micro_usd: int, at=None) -> None:
        async with self.uow as uow:
            await uow.model_usage.create(
                {
                    "purpose": "Test call",
                    "model": OPUS,
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "cost_micro_usd": cost_micro_usd,
                    "at": at or FROZEN_NOW,
                }
            )

    async def test_refuse_if_spent_with_nothing_spent_yet_lets_the_call_through(self):
        await self.build_budget().refuse_if_spent()

    async def test_refuse_if_spent_under_the_daily_allowance_lets_the_call_through(self):
        await self.seed_usage(round(0.9 * A_DOLLAR))

        await self.build_budget(daily_usd=1.0).refuse_if_spent()

    async def test_refuse_if_spent_at_the_daily_allowance_refuses_as_a_daily_one(self):
        await self.seed_usage(A_DOLLAR)

        with self.assertRaises(BudgetSpent) as context:
            await self.build_budget(daily_usd=1.0).refuse_if_spent()

        self.assertTrue(context.exception.is_daily)
        self.assertEqual(str(context.exception), "The model budget for this period is spent")

    async def test_refuse_if_spent_over_the_month_refuses_as_a_monthly_one(self):
        """Yesterday's spending is gone from the day and still counted in the month."""
        await self.seed_usage(round(9.5 * A_DOLLAR), at=FROZEN_NOW - timedelta(days=3))

        with self.assertRaises(BudgetSpent) as context:
            await self.build_budget(daily_usd=1.0, monthly_usd=9.0).refuse_if_spent()

        self.assertFalse(context.exception.is_daily)

    async def test_refuse_if_spent_ignores_what_was_spent_before_the_rolling_month(self):
        await self.seed_usage(round(99.0 * A_DOLLAR), at=FROZEN_NOW - timedelta(days=31))

        await self.build_budget(daily_usd=1.0, monthly_usd=10.0).refuse_if_spent()

    async def test_refuse_if_spent_ignores_yesterdays_spending_for_the_day(self):
        await self.seed_usage(round(5.0 * A_DOLLAR), at=FROZEN_NOW - timedelta(days=1))

        await self.build_budget(daily_usd=1.0, monthly_usd=100.0).refuse_if_spent()

    async def test_record_writes_the_call_down_priced(self):
        await self.build_budget().record(purpose="Photo review", model=OPUS, input_tokens=1300, output_tokens=80)

        async with self.uow as uow:
            written = await uow.model_usage.list_since(FROZEN_NOW - timedelta(days=1))
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0].purpose, "Photo review")
        self.assertEqual(written[0].model, OPUS)
        self.assertEqual(written[0].input_tokens, 1300)
        self.assertEqual(written[0].output_tokens, 80)
        self.assertEqual(written[0].cost_micro_usd, 6800)

    async def test_recorded_calls_add_up_until_the_allowance_is_gone(self):
        """Three reviews at $0.0068 each pass $0.02, and the fourth caller is turned away."""
        budget = self.build_budget(daily_usd=0.02)
        for _ in range(3):
            await budget.record(purpose="Photo review", model=OPUS, input_tokens=1300, output_tokens=80)

        with self.assertRaises(BudgetSpent):
            await budget.refuse_if_spent()
