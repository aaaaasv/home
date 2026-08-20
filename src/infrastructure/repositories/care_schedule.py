from datetime import date

from sqlalchemy import select

from src.common.constants import CareTaskType
from src.infrastructure.db.models import CareSchedule, Plant
from src.infrastructure.repositories.base import SQLAlchemyRepository


class CareScheduleRepository(SQLAlchemyRepository[CareSchedule]):
    model = CareSchedule

    async def list_by_plant_id(self, plant_id: int) -> list[CareSchedule]:
        result = await self.session.execute(
            select(CareSchedule).where(CareSchedule.plant_id == plant_id).order_by(CareSchedule.task_type)
        )
        return list(result.scalars().all())

    async def list_by_plant_ids(self, plant_ids: list[int]) -> list[CareSchedule]:
        result = await self.session.execute(
            select(CareSchedule).where(CareSchedule.plant_id.in_(plant_ids)).order_by(CareSchedule.task_type)
        )
        return list(result.scalars().all())

    async def retrieve_for_plant(self, plant_id: int, task_type: CareTaskType) -> CareSchedule | None:
        result = await self.session.execute(
            select(CareSchedule).where(CareSchedule.plant_id == plant_id, CareSchedule.task_type == task_type)
        )
        return result.scalar_one_or_none()

    async def list_due_with_plants(self, today: date) -> list[tuple[CareSchedule, Plant]]:
        result = await self.session.execute(
            select(CareSchedule, Plant)
            .join(Plant, Plant.id == CareSchedule.plant_id)
            .where(Plant.is_archived.is_(False), CareSchedule.next_due_on <= today)
            .order_by(CareSchedule.next_due_on, Plant.name, CareSchedule.task_type)
        )
        return [(schedule, plant) for schedule, plant in result.all()]
