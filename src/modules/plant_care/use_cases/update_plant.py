from src.common.exceptions import AlreadyExistsError, DoesNotExistError
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import UpdatePlantCommand


class UpdatePlantUseCase(BaseUseCase):
    async def __call__(self, command: UpdatePlantCommand) -> None:
        changes = command.build_changes()

        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(command.plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {command.plant_id} not found")

            if "name" in changes:
                await self._reject_taken_name(uow, changes["name"], command.plant_id)

            await uow.plants.update(command.plant_id, changes)

    async def _reject_taken_name(self, uow: UnitOfWork, name: str, plant_id: int) -> None:
        namesake = await uow.plants.retrieve_active_by_name(name)
        if namesake is not None and namesake.id != plant_id:
            raise AlreadyExistsError(f"Plant '{name}' already exists")
