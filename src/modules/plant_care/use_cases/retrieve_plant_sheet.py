from datetime import timedelta

from src.common.constants import CareTaskType
from src.common.exceptions import DoesNotExistError
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import PlantSheet

CLIMATE_WINDOW_HOURS = 48
SHEET_HISTORY_SIZE = 40


class RetrievePlantSheetUseCase(BaseUseCase):
    """
    Everything a specimen sheet shows about one plant, gathered in a single pass.

    the telegram card answers "what needs doing"; this answers "what is this plant" — so it carries the
    things a card has no room for: who tends it, the rhythm they actually keep, and the room's own weather.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, plant_id: int) -> PlantSheet:
        today = self.household_calendar.today()
        since = self.household_calendar.now() - timedelta(hours=CLIMATE_WINDOW_HOURS)

        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {plant_id} not found")

            schedules = await uow.care_schedules.list_by_plant_id(plant_id)
            recent_events = await uow.care_events.list_recent_by_plant_id(plant_id, limit=SHEET_HISTORY_SIZE)
            photos = await uow.plant_photos.list_by_plant_id(plant_id)
            carers = await uow.care_events.count_by_carer(plant_id, CareTaskType.WATERING)
            waterings = await uow.care_events.list_performed_at(plant_id, CareTaskType.WATERING)
            climate = await uow.room_climate_readings.list_hourly_averages(since)
            latest_climate = await uow.room_climate_readings.retrieve_latest()

        return PlantSheet.from_models(
            plant=plant,
            schedules=schedules,
            recent_events=recent_events,
            photos=photos,
            carers=carers,
            waterings=waterings,
            climate=climate,
            latest_climate=latest_climate,
            today=today,
        )
