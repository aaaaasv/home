from datetime import datetime

from sqlalchemy import select

from src.infrastructure.db.models import GridEvent
from src.infrastructure.repositories.base import SQLAlchemyRepository


class GridEventRepository(SQLAlchemyRepository[GridEvent]):
    model = GridEvent

    async def list_since(self, moment: datetime) -> list[GridEvent]:
        result = await self.session.execute(select(GridEvent).where(GridEvent.at >= moment).order_by(GridEvent.at))
        return list(result.scalars().all())

    async def retrieve_latest(self) -> GridEvent | None:
        result = await self.session.execute(select(GridEvent).order_by(GridEvent.at.desc()))
        return result.scalars().first()
