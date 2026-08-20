from src.common.use_case import BaseUseCase
from src.modules.places.commands import RemovePlaceCommand
from src.modules.places.domain import PlacesList


class RemovePlaceUseCase(BaseUseCase):
    """Drops a place entirely — for a mistaken entry, unlike marking it visited which keeps it as a memory"""

    async def __call__(self, command: RemovePlaceCommand) -> PlacesList:
        async with self.uow as uow:
            place = await uow.places.retrieve(command.place_id)
            if place is not None:
                await uow.places.delete(place.id)

            return PlacesList.from_places(await uow.places.list_all())
