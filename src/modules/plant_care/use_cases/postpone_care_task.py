from src.common.exceptions import DoesNotExistError
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import PostponeCareTaskCommand
from src.modules.plant_care.domain import PostponedCareTask, calculate_defer_days


class PostponeCareTaskUseCase(BaseUseCase):
    """Pushes a due task a little further out without recording care — nothing was performed, only deferred"""

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, command: PostponeCareTaskCommand) -> PostponedCareTask:
        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(command.plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {command.plant_id} not found")

            schedule = await uow.care_schedules.retrieve_for_plant(command.plant_id, command.task_type)
            if schedule is None:
                raise DoesNotExistError(f"Plant '{plant.name}' has no {command.task_type} schedule")

            defer_days = calculate_defer_days(command.task_type, schedule.interval_days)
            next_due_on = self.household_calendar.next_due_on(command.postponed_at, defer_days)
            await uow.care_schedules.update(schedule.id, {"next_due_on": next_due_on})

            return PostponedCareTask(
                plant_id=plant.id,
                plant_name=plant.name,
                task_type=command.task_type,
                next_due_on=next_due_on,
            )
