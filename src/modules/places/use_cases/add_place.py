from src.common.use_case import BaseActorUseCase
from src.modules.places.commands import AddPlaceCommand
from src.modules.places.domain import PlacesList


class AddPlaceUseCase(BaseActorUseCase):
    async def __call__(self, command: AddPlaceCommand) -> PlacesList:
        async with self.uow as uow:
            # the same place written twice is the family being a family — the first one already stands
            if await uow.places.retrieve_unvisited_by_name(command.name) is None:
                await uow.places.create(
                    {
                        "name": command.name,
                        "link": command.link,
                        "added_by_telegram_user_id": self.actor.telegram_user_id,
                        "added_by_display_name": self.actor.display_name,
                    }
                )

            return PlacesList.from_places(await uow.places.list_all())
