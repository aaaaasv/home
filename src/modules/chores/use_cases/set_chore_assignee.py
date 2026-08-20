from src.common.use_case import BaseUseCase
from src.modules.chores.commands import SetChoreAssigneeCommand
from src.modules.chores.domain import ChoresList


class SetChoreAssigneeUseCase(BaseUseCase):
    """Tags a chore to a person (or clears it) — its deadline card then @mentions them so the reminder reaches them"""

    async def __call__(self, command: SetChoreAssigneeCommand) -> ChoresList:
        async with self.uow as uow:
            chore = await uow.chores.retrieve_open(command.chore_id)
            if chore is not None:
                await uow.chores.update(
                    chore.id,
                    {
                        "assignee_telegram_user_id": command.assignee_telegram_user_id,
                        "assignee_display_name": command.assignee_display_name,
                    },
                )

            return ChoresList.from_chores(await uow.chores.list_all())
