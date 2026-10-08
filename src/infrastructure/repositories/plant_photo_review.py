from sqlalchemy import select

from src.infrastructure.db.models import PlantPhotoReviewRecord
from src.infrastructure.repositories.base import SQLAlchemyRepository


class PlantPhotoReviewRepository(SQLAlchemyRepository[PlantPhotoReviewRecord]):
    model = PlantPhotoReviewRecord

    async def list_by_plant_id(self, plant_id: int) -> list[PlantPhotoReviewRecord]:
        result = await self.session.execute(
            select(PlantPhotoReviewRecord)
            .where(PlantPhotoReviewRecord.plant_id == plant_id)
            .order_by(PlantPhotoReviewRecord.at)
        )
        return list(result.scalars().all())

    async def list_worth_remembering(self, plant_id: int, limit: int) -> list[PlantPhotoReviewRecord]:
        """
        The newest reviews that said something was wrong — never the «all is well» ones.

        a reviewer handed its own past verdicts anchors on them, and an «ok» from August confirms itself
        for free. only the ones that claimed a problem are worth checking against what the plant did next.
        """
        result = await self.session.execute(
            select(PlantPhotoReviewRecord)
            .where(PlantPhotoReviewRecord.plant_id == plant_id, PlantPhotoReviewRecord.status != "ok")
            .order_by(PlantPhotoReviewRecord.at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))
