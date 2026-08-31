from sqlalchemy import or_, select

from src.infrastructure.db.models import Plant
from src.infrastructure.repositories.base import SQLAlchemyRepository


class PlantRepository(SQLAlchemyRepository[Plant]):
    model = Plant

    async def list_active(self) -> list[Plant]:
        result = await self.session.execute(select(Plant).where(Plant.is_archived.is_(False)).order_by(Plant.name))
        return list(result.scalars().all())

    async def list_all(self) -> list[Plant]:
        """Every plant the household has ever kept, the archived ones included — the herbarium shows its dead."""
        result = await self.session.execute(select(Plant).order_by(Plant.name))
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

    async def retrieve_active_by_slug(self, slug: str) -> Plant | None:
        result = await self.session.execute(select(Plant).where(Plant.slug == slug, Plant.is_archived.is_(False)))
        return result.scalars().first()

    async def retrieve_by_slug(self, slug: str) -> Plant | None:
        """Unlike retrieve_active_by_slug this still finds an archived plant, because its sheet outlives it."""
        result = await self.session.execute(select(Plant).where(Plant.slug == slug))
        return result.scalars().first()

    async def list_offspring(self, plant_id: int) -> list[Plant]:
        """The cuttings taken from this plant, archived ones included — a lineage keeps its dead."""
        result = await self.session.execute(
            select(Plant).where(Plant.propagated_from_plant_id == plant_id).order_by(Plant.created_at)
        )
        return list(result.scalars().all())

    async def list_slugs(self) -> set[str]:
        result = await self.session.execute(select(Plant.slug).where(Plant.slug.is_not(None)))
        return set(result.scalars().all())
