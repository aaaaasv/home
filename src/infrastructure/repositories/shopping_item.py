from sqlalchemy import func, select

from src.infrastructure.db.models import ShoppingItem
from src.infrastructure.repositories.base import SQLAlchemyRepository


class ShoppingItemRepository(SQLAlchemyRepository[ShoppingItem]):
    model = ShoppingItem

    async def list_unbought(self) -> list[ShoppingItem]:
        result = await self.session.execute(
            select(ShoppingItem).where(ShoppingItem.bought_at.is_(None)).order_by(ShoppingItem.created_at)
        )
        return list(result.scalars().all())

    async def list_tracked(self) -> list[ShoppingItem]:
        result = await self.session.execute(
            select(ShoppingItem)
            .where(ShoppingItem.bought_at.is_(None), ShoppingItem.hotline_url.is_not(None))
            .order_by(ShoppingItem.created_at)
        )
        return list(result.scalars().all())

    async def retrieve_unbought_by_url(self, hotline_url: str) -> ShoppingItem | None:
        result = await self.session.execute(
            select(ShoppingItem).where(ShoppingItem.hotline_url == hotline_url, ShoppingItem.bought_at.is_(None))
        )
        return result.scalars().first()

    async def retrieve_unbought(self, item_id: int) -> ShoppingItem | None:
        result = await self.session.execute(
            select(ShoppingItem).where(ShoppingItem.id == item_id, ShoppingItem.bought_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def retrieve_unbought_by_name(self, name: str) -> ShoppingItem | None:
        result = await self.session.execute(
            select(ShoppingItem).where(func.lower(ShoppingItem.name) == name.lower(), ShoppingItem.bought_at.is_(None))
        )
        return result.scalars().first()
