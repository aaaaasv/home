from src.common.use_case import BaseUseCase
from src.modules.chores.commands import RenameChoreCommand
from src.modules.chores.domain import ChoresList


class RenameChoreUseCase(BaseUseCase):
    """Fixes a chore's wording — a typo, or a clearer phrasing — without touching its deadline"""

    async def __call__(self, command: RenameChoreCommand) -> ChoresList:
        async with self.uow as uow:
            chore = await uow.chores.retrieve_open(command.chore_id)
            if chore is not None:
                await uow.chores.update(chore.id, {"name": command.name.strip()})

            return ChoresList.from_chores(await uow.chores.list_all())
