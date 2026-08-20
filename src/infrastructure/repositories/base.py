from typing import Any, Generic, Sequence, Type, TypeVar

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.base import Base

T = TypeVar("T", bound=Base)


class SQLAlchemyRepository(Generic[T]):
    model: Type[T]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, data: dict[str, Any]) -> T:
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def retrieve(self, id: int) -> T | None:
        result = await self.session.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def update(self, id: int, data: dict[str, Any]) -> T | None:
        result = await self.session.execute(
            update(self.model).where(self.model.id == id).values(**data).returning(self.model)
        )
        return result.scalar_one_or_none()

    async def delete(self, id: int) -> int:
        result = await self.session.execute(delete(self.model).where(self.model.id == id))
        return result.rowcount or 0

    async def list(self, **filters: Any) -> Sequence[T]:
        result = await self.session.execute(select(self.model).filter_by(**filters))
        return result.scalars().all()
