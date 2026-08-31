from src.common.constants import CareTaskType
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import DrawerEntry

UKRAINIAN_ALPHABET = "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя"


def by_ukrainian_alphabet(name: str) -> list[int]:
    """Sort keys in the alphabet's own order — sqlite and python both order by codepoint, which puts і before а."""
    return [UKRAINIAN_ALPHABET.find(character) for character in name.casefold()]


class RetrieveDrawerUseCase(BaseUseCase):
    """
    Every plant the household has kept as a folder in a drawer, the archived ones among them.

    a tag on a pot opens one sheet, and until this existed that sheet was the whole collection as far as a
    guest could tell — this is the index that lets them reach the other four. a plant that died stays in the
    drawer because a herbarium is a record, not an inventory: it is filed among the rest and marked as gone.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self) -> list[DrawerEntry]:
        today = self.household_calendar.today()

        async with self.uow as uow:
            plants = await uow.plants.list_all()
            plant_ids = [plant.id for plant in plants]
            schedules = await uow.care_schedules.list_by_plant_ids(plant_ids)
            cover_photo_ids = await uow.plant_photos.latest_ids(plant_ids)

        watering = {s.plant_id: s for s in schedules if CareTaskType(s.task_type) is CareTaskType.WATERING}
        return [
            DrawerEntry.from_models(plant, watering.get(plant.id), cover_photo_ids.get(plant.id), today)
            for plant in sorted(plants, key=lambda plant: by_ukrainian_alphabet(plant.name))
        ]
