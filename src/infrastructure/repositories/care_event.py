from sqlalchemy import select

from src.common.constants import CareTaskType
from src.infrastructure.db.models import CareEvent, Plant
from src.infrastructure.repositories.base import SQLAlchemyRepository


class CareEventRepository(SQLAlchemyRepository[CareEvent]):
    model = CareEvent

    async def retrieve_latest(self, plant_id: int, task_type: CareTaskType) -> CareEvent | None:
        result = await self.session.execute(
            select(CareEvent)
            .where(CareEvent.plant_id == plant_id, CareEvent.task_type == task_type)
            .order_by(CareEvent.performed_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def list_recent_by_plant_id(self, plant_id: int, limit: int) -> list[CareEvent]:
        result = await self.session.execute(
            select(CareEvent).where(CareEvent.plant_id == plant_id).order_by(CareEvent.performed_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def list_recent_with_plants(self, limit: int) -> list[tuple[CareEvent, Plant]]:
        result = await self.session.execute(
            select(CareEvent, Plant)
            .join(Plant, Plant.id == CareEvent.plant_id)
            .order_by(CareEvent.performed_at.desc())
            .limit(limit)
        )
        return [(event, plant) for event, plant in result.all()]
