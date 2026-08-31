from src.common.exceptions import DoesNotExistError
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import ArchivePlantCommand


class ArchivePlantUseCase(BaseUseCase):
    """Takes a plant out of the household's care and records the day it ended"""

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, command: ArchivePlantCommand) -> str:
        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(command.plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {command.plant_id} not found")

            await uow.plants.update(
                command.plant_id,
                {"is_archived": True, "archived_on": self.household_calendar.today()},
            )
            return plant.name
