from sqlalchemy import func, select

from src.infrastructure.db.models import PlantPhoto
from src.infrastructure.repositories.base import SQLAlchemyRepository


class PlantPhotoRepository(SQLAlchemyRepository[PlantPhoto]):
    model = PlantPhoto

    async def list_by_plant_id(self, plant_id: int) -> list[PlantPhoto]:
        result = await self.session.execute(
            select(PlantPhoto).where(PlantPhoto.plant_id == plant_id).order_by(PlantPhoto.taken_at.asc())
        )
        return list(result.scalars().all())

    async def retrieve_latest(self, plant_id: int) -> PlantPhoto | None:
        result = await self.session.execute(
            select(PlantPhoto).where(PlantPhoto.plant_id == plant_id).order_by(PlantPhoto.taken_at.desc()).limit(1)
        )
        return result.scalars().first()

    async def latest_file_ids(self, plant_ids: list[int]) -> dict[int, str]:
        if not plant_ids:
            return {}
        latest = (
            select(PlantPhoto.plant_id, func.max(PlantPhoto.taken_at).label("taken_at"))
            .where(PlantPhoto.plant_id.in_(plant_ids))
            .group_by(PlantPhoto.plant_id)
            .subquery()
        )
        result = await self.session.execute(
            select(PlantPhoto).join(
                latest,
                (PlantPhoto.plant_id == latest.c.plant_id) & (PlantPhoto.taken_at == latest.c.taken_at),
            )
        )
        return {photo.plant_id: photo.telegram_file_id for photo in result.scalars()}

    async def latest_ids(self, plant_ids: list[int]) -> dict[int, int]:
        """The newest photo's own id per plant — what the drawer needs to show a cover."""
        if not plant_ids:
            return {}
        latest = (
            select(PlantPhoto.plant_id, func.max(PlantPhoto.taken_at).label("taken_at"))
            .where(PlantPhoto.plant_id.in_(plant_ids))
            .group_by(PlantPhoto.plant_id)
            .subquery()
        )
        result = await self.session.execute(
            select(PlantPhoto.plant_id, PlantPhoto.id).join(
                latest,
                (PlantPhoto.plant_id == latest.c.plant_id) & (PlantPhoto.taken_at == latest.c.taken_at),
            )
        )
        return {plant_id: photo_id for plant_id, photo_id in result.all()}
