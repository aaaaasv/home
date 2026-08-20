from src.common.use_case import BaseActorUseCase
from src.modules.chores.commands import AddChoreCommand
from src.modules.chores.domain import ChoresList


class AddChoreUseCase(BaseActorUseCase):
    async def __call__(self, command: AddChoreCommand) -> ChoresList:
        async with self.uow as uow:
            # the same chore written twice is the family being a family — the first one already stands
            if await uow.chores.retrieve_open_by_name(command.name) is None:
                await uow.chores.create(
                    {
                        "name": command.name,
                        "due_on": command.due_on,
                        "assignee_telegram_user_id": command.assignee_telegram_user_id,
                        "assignee_display_name": command.assignee_display_name,
                        "added_by_telegram_user_id": self.actor.telegram_user_id,
                        "added_by_display_name": self.actor.display_name,
                    }
                )

            return ChoresList.from_chores(await uow.chores.list_all())
