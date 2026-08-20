from sqlalchemy import select

from src.infrastructure.db.models import Place
from src.infrastructure.repositories.base import SQLAlchemyRepository


class PlaceRepository(SQLAlchemyRepository[Place]):
    model = Place

    async def list_all(self) -> list[Place]:
        result = await self.session.execute(select(Place).order_by(Place.created_at))
        return list(result.scalars().all())

    async def retrieve_unvisited(self, place_id: int) -> Place | None:
        result = await self.session.execute(select(Place).where(Place.id == place_id, Place.visited_at.is_(None)))
        return result.scalar_one_or_none()

    async def retrieve_unvisited_by_name(self, name: str) -> Place | None:
        # sqlite's lower() only folds ascii, so cyrillic case-insensitivity is done in python over the short list
        result = await self.session.execute(select(Place).where(Place.visited_at.is_(None)))
        lowered = name.lower()
        return next((place for place in result.scalars() if place.name.lower() == lowered), None)
