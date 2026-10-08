from datetime import datetime

from sqlalchemy import func, select

from src.infrastructure.db.models import ModelUsage
from src.infrastructure.repositories.base import SQLAlchemyRepository


class ModelUsageRepository(SQLAlchemyRepository[ModelUsage]):
    model = ModelUsage

    async def total_cost_since(self, moment: datetime) -> int:
        """What the paid models have cost since this moment, in millionths of a dollar."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(ModelUsage.cost_micro_usd), 0)).where(ModelUsage.at >= moment)
        )
        return int(result.scalar_one())

    async def list_since(self, moment: datetime) -> list[ModelUsage]:
        result = await self.session.execute(select(ModelUsage).where(ModelUsage.at >= moment).order_by(ModelUsage.at))
        return list(result.scalars().all())

    async def delete_before(self, moment: datetime) -> None:
        result = await self.session.execute(select(ModelUsage).where(ModelUsage.at < moment))
        for usage in result.scalars().all():
            await self.session.delete(usage)
