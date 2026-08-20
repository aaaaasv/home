from src.common.exceptions import AlreadyExistsError, DoesNotExistError
from src.common.use_case import BaseUseCase
from src.modules.plant_care.commands import RestorePlantCommand


class RestorePlantUseCase(BaseUseCase):
    """Brings an archived plant back with its schedules, photos and history intact"""

    async def __call__(self, command: RestorePlantCommand) -> str:
        async with self.uow as uow:
            plant = await uow.plants.retrieve(command.plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {command.plant_id} not found")
            if not plant.is_archived:
                return plant.name

            # only one active plant may hold a name, so one added meanwhile under the same name blocks the return
            if await uow.plants.retrieve_active_by_name(plant.name) is not None:
                raise AlreadyExistsError(f"An active plant named '{plant.name}' already exists")

            await uow.plants.update(command.plant_id, {"is_archived": False})
            return plant.name
