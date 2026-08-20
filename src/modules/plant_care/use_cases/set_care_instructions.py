from src.common.exceptions import DoesNotExistError
from src.common.use_case import BaseUseCase
from src.modules.plant_care.commands import SetCareInstructionsCommand


class SetCareInstructionsUseCase(BaseUseCase):
    async def __call__(self, command: SetCareInstructionsCommand) -> None:
        async with self.uow as uow:
            schedule = await uow.care_schedules.retrieve_for_plant(command.plant_id, command.task_type)
            if schedule is None:
                raise DoesNotExistError(f"No {command.task_type} schedule for plant {command.plant_id}")
            await uow.care_schedules.update(schedule.id, {"instructions": command.instructions})
