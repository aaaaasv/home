from src.common.use_case import BaseUseCase
from src.modules.chores.commands import RemoveChoreCommand
from src.modules.chores.domain import ChoresList


class RemoveChoreUseCase(BaseUseCase):
    """Drops a chore entirely — for a mistaken entry, unlike completing it which records who did it"""

    async def __call__(self, command: RemoveChoreCommand) -> ChoresList:
        async with self.uow as uow:
            chore = await uow.chores.retrieve(command.chore_id)
            if chore is not None:
                await uow.chores.delete(chore.id)

            return ChoresList.from_chores(await uow.chores.list_all())
