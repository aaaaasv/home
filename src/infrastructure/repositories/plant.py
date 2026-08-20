from sqlalchemy import or_, select

from src.infrastructure.db.models import Plant
from src.infrastructure.repositories.base import SQLAlchemyRepository


class PlantRepository(SQLAlchemyRepository[Plant]):
    model = Plant

    async def list_active(self) -> list[Plant]:
        result = await self.session.execute(select(Plant).where(Plant.is_archived.is_(False)).order_by(Plant.name))
        return list(result.scalars().all())

    async def list_active_with_climate_range(self) -> list[Plant]:
        result = await self.session.execute(
            select(Plant)
            .where(
                Plant.is_archived.is_(False),
                or_(
                    Plant.ideal_temperature_min_celsius.is_not(None),
                    Plant.ideal_humidity_min_percent.is_not(None),
                ),
            )
            .order_by(Plant.name)
        )
        return list(result.scalars().all())

    async def retrieve_active(self, plant_id: int) -> Plant | None:
        result = await self.session.execute(select(Plant).where(Plant.id == plant_id, Plant.is_archived.is_(False)))
        return result.scalar_one_or_none()

    async def retrieve_active_by_name(self, name: str) -> Plant | None:
        result = await self.session.execute(select(Plant).where(Plant.name == name, Plant.is_archived.is_(False)))
        return result.scalar_one_or_none()
