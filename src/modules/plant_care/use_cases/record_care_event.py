from datetime import timedelta

from src.common.constants import CareTaskType
from src.common.domain import Actor
from src.common.exceptions import DoesNotExistError, RecentCareExistsError
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseActorUseCase
from src.infrastructure.db.models import CareEvent, Plant
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import RecordCareEventCommand
from src.modules.plant_care.domain import CareRecord


class RecordCareEventUseCase(BaseActorUseCase):
    def __init__(
        self, uow: UnitOfWork, actor: Actor, household_calendar: HouseholdCalendar, recent_care_guard_hours: int
    ):
        super().__init__(uow, actor)
        self.household_calendar = household_calendar
        self.recent_care_guard_hours = recent_care_guard_hours

    async def __call__(self, command: RecordCareEventCommand) -> CareRecord:
        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(command.plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {command.plant_id} not found")

            schedule = await uow.care_schedules.retrieve_for_plant(command.plant_id, command.task_type)
            if schedule is None:
                raise DoesNotExistError(f"Plant '{plant.name}' has no {command.task_type} schedule")

            if not command.force:
                latest_event = await uow.care_events.retrieve_latest(command.plant_id, command.task_type)
                self._reject_repeated_care(latest_event, plant, command)

            await uow.care_events.create(
                {
                    "plant_id": command.plant_id,
                    "task_type": command.task_type,
                    "performed_at": command.performed_at,
                    "performed_by_telegram_user_id": self.actor.telegram_user_id,
                    "performed_by_display_name": self.actor.display_name,
                    "note": command.note,
                    "previous_next_due_on": schedule.next_due_on,
                }
            )
            next_due_on = self.household_calendar.next_due_on(command.performed_at, schedule.interval_days)
            await uow.care_schedules.update(
                schedule.id, {"last_performed_at": command.performed_at, "next_due_on": next_due_on}
            )

            return CareRecord(
                plant_id=plant.id,
                plant_name=plant.name,
                task_type=CareTaskType(command.task_type),
                performed_by_display_name=self.actor.display_name,
                next_due_on=next_due_on,
            )

    def _reject_repeated_care(
        self, latest_event: CareEvent | None, plant: Plant, command: RecordCareEventCommand
    ) -> None:
        if latest_event is None:
            return
        if command.performed_at - latest_event.performed_at >= timedelta(hours=self.recent_care_guard_hours):
            return

        raise RecentCareExistsError(
            detail=(
                f"Plant '{plant.name}' already had {command.task_type} "
                f"from {latest_event.performed_by_display_name} within the last "
                f"{self.recent_care_guard_hours} hours"
            ),
            plant_name=plant.name,
            task_type=CareTaskType(command.task_type),
            performed_at=latest_event.performed_at,
            performed_by_display_name=latest_event.performed_by_display_name,
        )
