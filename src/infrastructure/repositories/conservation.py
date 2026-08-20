from typing import Any

from sqlalchemy import select

from src.infrastructure.db.models import ConservationRecord
from src.infrastructure.repositories.base import SQLAlchemyRepository


class ConservationRepository(SQLAlchemyRepository[ConservationRecord]):
    """The station's storage state is a single row — get it, or upsert it"""

    model = ConservationRecord

    async def get(self) -> ConservationRecord | None:
        result = await self.session.execute(select(ConservationRecord).order_by(ConservationRecord.id).limit(1))
        return result.scalar_one_or_none()

    async def save(self, data: dict[str, Any]) -> ConservationRecord:
        existing = await self.get()
        if existing is None:
            return await self.create(data)
        return await self.update(existing.id, data)
