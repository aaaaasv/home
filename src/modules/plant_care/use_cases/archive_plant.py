from src.common.exceptions import DoesNotExistError
from src.common.use_case import BaseUseCase
from src.modules.plant_care.commands import ArchivePlantCommand


class ArchivePlantUseCase(BaseUseCase):
    async def __call__(self, command: ArchivePlantCommand) -> str:
        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(command.plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {command.plant_id} not found")

            await uow.plants.update(command.plant_id, {"is_archived": True})
            return plant.name
