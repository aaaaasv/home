from src.common.constants import PLANT_CARD_HISTORY_SIZE
from src.common.exceptions import DoesNotExistError
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import PlantCard


class RetrievePlantCardUseCase(BaseUseCase):
    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, plant_id: int) -> PlantCard:
        today = self.household_calendar.today()

        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {plant_id} not found")

            schedules = await uow.care_schedules.list_by_plant_id(plant_id)
            recent_events = await uow.care_events.list_recent_by_plant_id(plant_id, limit=PLANT_CARD_HISTORY_SIZE)
            photos = await uow.plant_photos.list_by_plant_id(plant_id)

            return PlantCard.from_models(plant, schedules, recent_events, photos, today)
