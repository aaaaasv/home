from src.common.exceptions import ConflictError, DoesNotExistError
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import UndoCareEventCommand
from src.modules.plant_care.domain import DueCareTask


class UndoCareEventUseCase(BaseUseCase):
    """Takes back the latest care record for a task and puts the schedule back on the date that record replaced"""

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, command: UndoCareEventCommand) -> DueCareTask:
        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(command.plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {command.plant_id} not found")

            event = await uow.care_events.retrieve_latest(command.plant_id, command.task_type)
            if event is None:
                raise DoesNotExistError(f"Plant '{plant.name}' has no {command.task_type} to undo")

            schedule = await uow.care_schedules.retrieve_for_plant(command.plant_id, command.task_type)
            if schedule is None:
                # the schedule was removed after this care was recorded, so there is nothing to put back
                raise DoesNotExistError(f"Plant '{plant.name}' no longer has a {command.task_type} schedule")
            if event.previous_next_due_on is None:
                # recorded before migration 012, which is when the previous due date started being kept
                raise ConflictError(f"This {command.task_type} record is too old to undo")

            await uow.care_events.delete(event.id)

            # with the record gone, "last performed" is whatever came before it — or never, if this was the first
            earlier_event = await uow.care_events.retrieve_latest(command.plant_id, command.task_type)
            await uow.care_schedules.update(
                schedule.id,
                {
                    "next_due_on": event.previous_next_due_on,
                    "last_performed_at": earlier_event.performed_at if earlier_event else None,
                },
            )

            photo_file_ids = await uow.plant_photos.latest_file_ids([plant.id])

        return DueCareTask(
            plant_id=plant.id,
            plant_name=plant.name,
            task_type=command.task_type,
            interval_days=schedule.interval_days,
            overdue_days=(self.household_calendar.today() - event.previous_next_due_on).days,
            photo_file_id=photo_file_ids.get(plant.id),
            instructions=schedule.instructions,
        )
