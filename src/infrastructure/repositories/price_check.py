from datetime import datetime

from sqlalchemy import func, select

from src.infrastructure.db.models import PriceCheck
from src.infrastructure.repositories.base import SQLAlchemyRepository


class PriceCheckRepository(SQLAlchemyRepository[PriceCheck]):
    model = PriceCheck

    async def record(self, shopping_item_id: int, price: int, checked_at: datetime) -> None:
        await self.create({"shopping_item_id": shopping_item_id, "price": price, "checked_at": checked_at})

    async def retrieve_minimum(self, shopping_item_id: int) -> int | None:
        result = await self.session.execute(
            select(func.min(PriceCheck.price)).where(PriceCheck.shopping_item_id == shopping_item_id)
        )
        return result.scalar_one_or_none()

    async def retrieve_initial(self, shopping_item_id: int) -> int | None:
        result = await self.session.execute(
            select(PriceCheck.price)
            .where(PriceCheck.shopping_item_id == shopping_item_id)
            .order_by(PriceCheck.checked_at.asc())
            .limit(1)
        )
        return result.scalars().first()

    async def retrieve_latest(self, shopping_item_id: int) -> int | None:
        result = await self.session.execute(
            select(PriceCheck.price)
            .where(PriceCheck.shopping_item_id == shopping_item_id)
            .order_by(PriceCheck.checked_at.desc())
            .limit(1)
        )
        return result.scalars().first()
