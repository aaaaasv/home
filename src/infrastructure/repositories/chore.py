from datetime import date

from sqlalchemy import select

from src.infrastructure.db.models import Chore
from src.infrastructure.repositories.base import SQLAlchemyRepository


class ChoreRepository(SQLAlchemyRepository[Chore]):
    model = Chore

    async def list_all(self) -> list[Chore]:
        result = await self.session.execute(select(Chore).order_by(Chore.created_at))
        return list(result.scalars().all())

    async def retrieve_open(self, chore_id: int) -> Chore | None:
        result = await self.session.execute(select(Chore).where(Chore.id == chore_id, Chore.completed_at.is_(None)))
        return result.scalar_one_or_none()

    async def retrieve_open_by_name(self, name: str) -> Chore | None:
        # sqlite's lower() only folds ascii, so cyrillic case-insensitivity is done in python over the short list
        result = await self.session.execute(select(Chore).where(Chore.completed_at.is_(None)))
        lowered = name.lower()
        return next((chore for chore in result.scalars() if chore.name.lower() == lowered), None)

    async def list_open_due_on_or_before(self, cutoff: date) -> list[Chore]:
        result = await self.session.execute(
            select(Chore)
            .where(Chore.completed_at.is_(None), Chore.due_on.is_not(None), Chore.due_on <= cutoff)
            .order_by(Chore.due_on)
        )
        return list(result.scalars().all())
