from datetime import datetime

from sqlalchemy import select

from src.infrastructure.db.models import AirAlertState
from src.infrastructure.repositories.base import SQLAlchemyRepository


class AirAlertStateRepository(SQLAlchemyRepository[AirAlertState]):
    model = AirAlertState

    async def retrieve(self) -> AirAlertState | None:
        result = await self.session.execute(select(AirAlertState).order_by(AirAlertState.id))
        return result.scalars().first()

    async def save(self, level: str, reason: str | None, changed_at: datetime) -> None:
        """One row, rewritten — the history of alerts is somebody else's job, this only holds the latest."""
        existing = await self.retrieve()
        if existing is None:
            self.session.add(AirAlertState(level=level, reason=reason, changed_at=changed_at))
            return
        if existing.level != level:
            existing.changed_at = changed_at
        existing.level = level
        existing.reason = reason
