from datetime import timedelta

from src.common.constants import CareTaskType
from src.common.exceptions import DoesNotExistError
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import PlantSheet
from src.modules.plant_care.services.plant_air import read_plant_air

CLIMATE_WINDOW_HOURS = 48
SHEET_HISTORY_SIZE = 40


class RetrievePlantSheetUseCase(BaseUseCase):
    """
    Everything a specimen sheet shows about one plant, gathered in a single pass.

    the telegram card answers "what needs doing"; this answers "what is this plant" — so it carries the
    things a card has no room for: who tends it, the rhythm they actually keep, and the room's own weather.
    """

    def __init__(
        self, uow: UnitOfWork, household_calendar: HouseholdCalendar, sensor_by_plant: dict[int, str] | None = None
    ):
        super().__init__(uow)
        self.household_calendar = household_calendar
        self.sensor_by_plant = sensor_by_plant or {}

    async def __call__(self, reference: str) -> PlantSheet:
        """Reference is the slug a tag carries, or a plain id for anything written before slugs existed."""
        # an archived plant still has a sheet: the tag on its pot, and any link already shared, must keep working
        today = self.household_calendar.today()
        since = self.household_calendar.now() - timedelta(hours=CLIMATE_WINDOW_HOURS)

        async with self.uow as uow:
            plant = await uow.plants.retrieve_by_slug(reference)
            if plant is None and reference.isdigit():
                plant = await uow.plants.retrieve(int(reference))
            if plant is None:
                raise DoesNotExistError(f"Plant {reference} not found")
            plant_id = plant.id

            schedules = await uow.care_schedules.list_by_plant_id(plant_id)
            recent_events = await uow.care_events.list_recent_by_plant_id(plant_id, limit=SHEET_HISTORY_SIZE)
            photos = await uow.plant_photos.list_by_plant_id(plant_id)
            carers = await uow.care_events.count_by_carer(plant_id, CareTaskType.WATERING)
            waterings = await uow.care_events.list_performed_at(plant_id, CareTaskType.WATERING)
            # the sheet is opened by a guest standing next to the pot, so the numbers on it have to be that
            # pot's — the board on the hall shelf reads five degrees off and speaks for nowhere in particular
            air = await read_plant_air(
                uow, sensor=self.sensor_by_plant.get(plant_id), room=plant.room, now=self.household_calendar.now()
            )
            climate = await uow.sensor_readings.list_hourly_averages_for_room(plant.room, since) if plant.room else []
            current_names = await uow.family_members.map_current_names()
            parent = (
                await uow.plants.retrieve(plant.propagated_from_plant_id) if plant.propagated_from_plant_id else None
            )
            offspring = await uow.plants.list_offspring(plant_id)

        return PlantSheet.from_models(
            plant=plant,
            schedules=schedules,
            recent_events=recent_events,
            photos=photos,
            carers=carers,
            waterings=waterings,
            climate=climate,
            air=air,
            today=today,
            current_names=current_names,
            parent=parent,
            offspring=offspring,
        )
