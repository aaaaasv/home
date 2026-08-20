from datetime import date

from src.common.exceptions import DoesNotExistError
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.models import CareSchedule
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import SetCareScheduleCommand
from src.modules.plant_care.domain import CareScheduleDetails


class SetCareScheduleUseCase(BaseUseCase):
    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, command: SetCareScheduleCommand) -> CareScheduleDetails:
        today = self.household_calendar.today()

        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(command.plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {command.plant_id} not found")

            existing_schedule = await uow.care_schedules.retrieve_for_plant(command.plant_id, command.task_type)
            if existing_schedule is None:
                schedule = await uow.care_schedules.create(
                    {
                        "plant_id": command.plant_id,
                        "task_type": command.task_type,
                        "interval_days": command.interval_days,
                        "next_due_on": today,
                    }
                )
            else:
                schedule = await uow.care_schedules.update(
                    existing_schedule.id,
                    {
                        "interval_days": command.interval_days,
                        "next_due_on": self._reschedule(existing_schedule, command.interval_days, today),
                    },
                )

            return CareScheduleDetails.from_schedule(schedule, today)

    def _reschedule(self, schedule: CareSchedule, interval_days: int, today: date) -> date:
        if schedule.last_performed_at is None:
            return today
        return self.household_calendar.next_due_on(schedule.last_performed_at, interval_days)
