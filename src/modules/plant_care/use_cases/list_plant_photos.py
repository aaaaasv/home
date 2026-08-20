from src.common.exceptions import DoesNotExistError
from src.common.use_case import BaseUseCase
from src.modules.plant_care.domain import PlantPhotoDetails


class ListPlantPhotosUseCase(BaseUseCase):
    async def __call__(self, plant_id: int) -> list[PlantPhotoDetails]:
        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {plant_id} not found")

            photos = await uow.plant_photos.list_by_plant_id(plant_id)
            return [PlantPhotoDetails.from_photo(photo) for photo in photos]
