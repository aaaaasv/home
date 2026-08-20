from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.models import CareSchedule
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import CareScheduleDetails, PlantSummary


class ListPlantsUseCase(BaseUseCase):
    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self) -> list[PlantSummary]:
        today = self.household_calendar.today()

        async with self.uow as uow:
            plants = await uow.plants.list_active()
            if not plants:
                return []
            schedules = await uow.care_schedules.list_by_plant_ids([plant.id for plant in plants])

        schedules_by_plant_id = self._group_by_plant_id(schedules)
        return [
            PlantSummary(
                id=plant.id,
                name=plant.name,
                location=plant.location,
                schedules=[
                    CareScheduleDetails.from_schedule(schedule, today)
                    for schedule in schedules_by_plant_id.get(plant.id, [])
                ],
            )
            for plant in plants
        ]

    @staticmethod
    def _group_by_plant_id(schedules: list[CareSchedule]) -> dict[int, list[CareSchedule]]:
        grouped: dict[int, list[CareSchedule]] = {}
        for schedule in schedules:
            grouped.setdefault(schedule.plant_id, []).append(schedule)
        return grouped
