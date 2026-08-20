from src.common.use_case import BaseUseCase
from src.modules.chores.commands import SetChoreDeadlineCommand
from src.modules.chores.domain import ChoresList


class SetChoreDeadlineUseCase(BaseUseCase):
    """Sets or clears a chore's deadline — the one thing that turns a silent someday item into a reminded one"""

    async def __call__(self, command: SetChoreDeadlineCommand) -> ChoresList:
        async with self.uow as uow:
            chore = await uow.chores.retrieve_open(command.chore_id)
            if chore is not None:
                await uow.chores.update(chore.id, {"due_on": command.due_on})

            return ChoresList.from_chores(await uow.chores.list_all())
