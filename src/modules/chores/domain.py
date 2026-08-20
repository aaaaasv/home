from datetime import date, datetime

from src.common.domain import DomainModel
from src.infrastructure.db.models import Chore


class ChoreDetails(DomainModel):
    id: int
    name: str
    due_on: date | None
    added_by_display_name: str
    assignee_telegram_user_id: int | None
    assignee_display_name: str | None
    completed_at: datetime | None
    completed_by_display_name: str | None

    @classmethod
    def from_chore(cls, chore: Chore) -> "ChoreDetails":
        return cls(
            id=chore.id,
            name=chore.name,
            due_on=chore.due_on,
            added_by_display_name=chore.added_by_display_name,
            assignee_telegram_user_id=chore.assignee_telegram_user_id,
            assignee_display_name=chore.assignee_display_name,
            completed_at=chore.completed_at,
            completed_by_display_name=chore.completed_by_display_name,
        )

    @property
    def is_done(self) -> bool:
        return self.completed_at is not None


class ChoresList(DomainModel):
    # open chores with a deadline, soonest first — the only ones that ever speak
    dated: list[ChoreDetails]
    # open chores with no deadline — a silent «колись» pile that never nags
    someday: list[ChoreDetails]

    @classmethod
    def from_chores(cls, chores: list[Chore]) -> "ChoresList":
        open_chores = [ChoreDetails.from_chore(chore) for chore in chores if chore.completed_at is None]
        return cls(
            dated=sorted((chore for chore in open_chores if chore.due_on is not None), key=lambda chore: chore.due_on),
            someday=[chore for chore in open_chores if chore.due_on is None],
        )

    @property
    def open_chores(self) -> list["ChoreDetails"]:
        return self.dated + self.someday

    @property
    def is_empty(self) -> bool:
        return not self.dated and not self.someday


class ChoreReminder(DomainModel):
    """An open dated chore now inside its reminder window — what a deadline card renders from"""

    chore_id: int
    name: str
    days_until_due: int
    assignee_telegram_user_id: int | None = None
    assignee_display_name: str | None = None
