from sqlalchemy import func, select

from src.common.constants import PlantPhotoFrame
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

    async def list_cover_file_ids(self, plant_ids: list[int]) -> dict[int, str]:
        return {photo.plant_id: photo.telegram_file_id for photo in await self._list_covers(plant_ids)}

    async def list_cover_photo_ids(self, plant_ids: list[int]) -> dict[int, int]:
        return {photo.plant_id: photo.id for photo in await self._list_covers(plant_ids)}

    async def _list_covers(self, plant_ids: list[int]) -> list[PlantPhoto]:
        """Each plant's newest general frame — a close-up saved after it in the same album is not the plant."""
        if not plant_ids:
            return []
        is_overview = PlantPhoto.frame == PlantPhotoFrame.OVERVIEW.value
        newest = (
            select(PlantPhoto.plant_id, func.max(PlantPhoto.taken_at).label("taken_at"))
            .where(PlantPhoto.plant_id.in_(plant_ids), is_overview)
            .group_by(PlantPhoto.plant_id)
            .subquery()
        )
        result = await self.session.execute(
            select(PlantPhoto)
            .join(newest, (PlantPhoto.plant_id == newest.c.plant_id) & (PlantPhoto.taken_at == newest.c.taken_at))
            .where(is_overview)
        )
        return list(result.scalars().all())
