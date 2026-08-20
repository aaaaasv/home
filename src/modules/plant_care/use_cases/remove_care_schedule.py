from src.common.constants import CareTaskType
from src.common.exceptions import DoesNotExistError, ValidationError
from src.common.use_case import BaseUseCase
from src.modules.plant_care.commands import RemoveCareScheduleCommand


class RemoveCareScheduleUseCase(BaseUseCase):
    async def __call__(self, command: RemoveCareScheduleCommand) -> None:
        if command.task_type == CareTaskType.WATERING:
            raise ValidationError("Watering schedule cannot be removed")

        async with self.uow as uow:
            schedule = await uow.care_schedules.retrieve_for_plant(command.plant_id, command.task_type)
            if schedule is None:
                raise DoesNotExistError(f"Plant {command.plant_id} has no {command.task_type} schedule")

            await uow.care_schedules.delete(schedule.id)
