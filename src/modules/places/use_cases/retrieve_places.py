from src.common.use_case import BaseUseCase
from src.modules.places.domain import PlacesList


class RetrievePlacesUseCase(BaseUseCase):
    async def __call__(self) -> PlacesList:
        async with self.uow as uow:
            return PlacesList.from_places(await uow.places.list_all())
