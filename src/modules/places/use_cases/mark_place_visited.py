from datetime import datetime

from src.common.domain import Actor
from src.common.use_case import BaseActorUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.places.commands import MarkPlaceVisitedCommand
from src.modules.places.domain import PlacesList


class MarkPlaceVisitedUseCase(BaseActorUseCase):
    """Moves a place into the history of where the family has been, keeping who marked it and when"""

    def __init__(self, uow: UnitOfWork, actor: Actor, visited_at: datetime):
        super().__init__(uow, actor)
        self.visited_at = visited_at

    async def __call__(self, command: MarkPlaceVisitedCommand) -> PlacesList:
        async with self.uow as uow:
            place = await uow.places.retrieve_unvisited(command.place_id)
            if place is not None:
                await uow.places.update(
                    place.id,
                    {"visited_at": self.visited_at, "visited_by_display_name": self.actor.display_name},
                )

            return PlacesList.from_places(await uow.places.list_all())
