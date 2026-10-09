from datetime import datetime

from sqlalchemy import select

from src.infrastructure.db.models import AirConditionerRun
from src.infrastructure.repositories.base import SQLAlchemyRepository


class AirConditionerRunRepository(SQLAlchemyRepository[AirConditionerRun]):
    model = AirConditionerRun

    async def retrieve_open(self) -> AirConditionerRun | None:
        result = await self.session.execute(
            select(AirConditionerRun).where(AirConditionerRun.ended_at.is_(None)).order_by(AirConditionerRun.id.desc())
        )
        return result.scalars().first()

    async def list_since(self, moment: datetime) -> list[AirConditionerRun]:
        """Every run that started in the window — the summer's worth of them, which nothing read before."""
        result = await self.session.execute(
            select(AirConditionerRun)
            .where(AirConditionerRun.started_at >= moment)
            .order_by(AirConditionerRun.started_at)
        )
        return list(result.scalars().all())
