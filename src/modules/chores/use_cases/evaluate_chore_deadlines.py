from datetime import date, timedelta

from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.chores.domain import ChoreReminder


class EvaluateChoreDeadlinesUseCase(BaseUseCase):
    """
    The open chores whose deadline is close enough to deserve a card — today's date is the only clock.

    a chore with no deadline is never here, and one still far out is never here: it is the usually-empty set that
    earns the reminder its place, exactly like the care digest naming only what is due. the caller keeps one card
    per chore in this set, so a family with nothing due soon sees nothing.
    """

    def __init__(self, uow: UnitOfWork, today: date, lead_days: int):
        super().__init__(uow)
        self.today = today
        self.lead_days = lead_days

    async def __call__(self) -> list[ChoreReminder]:
        cutoff = self.today + timedelta(days=self.lead_days)
        async with self.uow as uow:
            chores = await uow.chores.list_open_due_on_or_before(cutoff)

        return [
            ChoreReminder(
                chore_id=chore.id,
                name=chore.name,
                days_until_due=(chore.due_on - self.today).days,
                assignee_telegram_user_id=chore.assignee_telegram_user_id,
                assignee_display_name=chore.assignee_display_name,
            )
            for chore in chores
        ]
