from src.common.use_case import BaseUseCase
from src.modules.places.commands import RenamePlaceCommand
from src.modules.places.domain import PlacesList


class RenamePlaceUseCase(BaseUseCase):
    """Fixes a place's name — a typo, or a clearer wording — without touching anything else about it"""

    async def __call__(self, command: RenamePlaceCommand) -> PlacesList:
        async with self.uow as uow:
            place = await uow.places.retrieve_unvisited(command.place_id)
            if place is not None:
                await uow.places.update(place.id, {"name": command.name.strip()})

            return PlacesList.from_places(await uow.places.list_all())
