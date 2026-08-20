from datetime import datetime

from src.common.domain import Actor
from src.common.use_case import BaseActorUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.chores.commands import CompleteChoreCommand
from src.modules.chores.domain import ChoresList


class CompleteChoreUseCase(BaseActorUseCase):
    """Marks a chore done — keeping who did it and when — and drops it from the open list for good"""

    def __init__(self, uow: UnitOfWork, actor: Actor, completed_at: datetime):
        super().__init__(uow, actor)
        self.completed_at = completed_at

    async def __call__(self, command: CompleteChoreCommand) -> ChoresList:
        async with self.uow as uow:
            chore = await uow.chores.retrieve_open(command.chore_id)
            if chore is not None:
                await uow.chores.update(
                    chore.id,
                    {"completed_at": self.completed_at, "completed_by_display_name": self.actor.display_name},
                )

            return ChoresList.from_chores(await uow.chores.list_all())
