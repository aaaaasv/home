from sqlalchemy import select

from src.common.constants import ClimateDimension
from src.infrastructure.db.models import PlantClimateAlert
from src.infrastructure.repositories.base import SQLAlchemyRepository


class PlantClimateAlertRepository(SQLAlchemyRepository[PlantClimateAlert]):
    model = PlantClimateAlert

    async def retrieve_latest(self, plant_id: int, dimension: ClimateDimension) -> PlantClimateAlert | None:
        result = await self.session.execute(
            select(PlantClimateAlert)
            .where(PlantClimateAlert.plant_id == plant_id, PlantClimateAlert.dimension == dimension)
            .order_by(PlantClimateAlert.id.desc())
        )
        return result.scalars().first()
