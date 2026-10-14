from datetime import datetime

from sqlalchemy import select

from src.infrastructure.db.models import SupplyDeclaration
from src.infrastructure.repositories.base import SQLAlchemyRepository


class SupplyDeclarationRepository(SQLAlchemyRepository[SupplyDeclaration]):
    model = SupplyDeclaration

    async def retrieve_current(self) -> SupplyDeclaration | None:
        result = await self.session.execute(select(SupplyDeclaration).order_by(SupplyDeclaration.id))
        return result.scalars().first()

    async def save(self, supply: str, declared_at: datetime) -> None:
        """One row, rewritten: this is what is true now, and the journal of outages is a different table."""
        existing = await self.retrieve_current()
        if existing is None:
            self.session.add(SupplyDeclaration(supply=supply, declared_at=declared_at))
            return
        existing.supply = supply
        existing.declared_at = declared_at
