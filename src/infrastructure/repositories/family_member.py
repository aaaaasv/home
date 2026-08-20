from sqlalchemy import select

from src.infrastructure.db.models import FamilyMember
from src.infrastructure.repositories.base import SQLAlchemyRepository


class FamilyMemberRepository(SQLAlchemyRepository[FamilyMember]):
    model = FamilyMember

    async def list_all(self) -> list[FamilyMember]:
        result = await self.session.execute(select(FamilyMember).order_by(FamilyMember.display_name))
        return list(result.scalars().all())

    async def upsert(self, telegram_user_id: int, display_name: str) -> None:
        existing = await self.session.get(FamilyMember, telegram_user_id)
        if existing is None:
            self.session.add(FamilyMember(telegram_user_id=telegram_user_id, display_name=display_name))
            return
        # only touch the row when the name actually changed, so onupdate does not churn on every message
        if existing.display_name != display_name:
            existing.display_name = display_name
