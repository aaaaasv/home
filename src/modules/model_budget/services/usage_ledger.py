"""The seam between a paid model client and the ledger that decides whether it may spend."""

from typing import Protocol


class BudgetSpent(Exception):
    """The allowance for the period is gone. `is_daily` says which one, because they clear differently."""

    def __init__(self, is_daily: bool):
        super().__init__("The model budget for this period is spent")
        self.is_daily = is_daily


class UsageLedger(Protocol):
    """
    What a model client needs from the budget: permission before, and the bill after.

    it is a protocol so the client stays an adapter — it knows that something counts the money, not that the
    counting happens in sqlite.
    """

    async def refuse_if_spent(self) -> None:
        """Raises BudgetSpent when this period's allowance is gone."""

    async def record(self, purpose: str, model: str, input_tokens: int, output_tokens: int) -> None:
        ...
