from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import CareDigest


class BuildCareDigestUseCase(BaseUseCase):
    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self) -> CareDigest:
        today = self.household_calendar.today()

        async with self.uow as uow:
            due_schedules = await uow.care_schedules.list_due_with_plants(today)
            photo_file_ids = await uow.plant_photos.latest_file_ids([plant.id for _, plant in due_schedules])

        return CareDigest.from_due_schedules(today, due_schedules, photo_file_ids)
