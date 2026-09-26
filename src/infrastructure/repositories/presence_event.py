from datetime import datetime

from sqlalchemy import select

from src.infrastructure.db.models import PresenceEvent
from src.infrastructure.repositories.base import SQLAlchemyRepository


class PresenceEventRepository(SQLAlchemyRepository[PresenceEvent]):
    model = PresenceEvent

    async def retrieve_last_departure(self, mac: str) -> PresenceEvent | None:
        """When this phone was last seen leaving — the only thing an absence can be measured from."""
        result = await self.session.execute(
            select(PresenceEvent)
            .where(PresenceEvent.mac == mac, PresenceEvent.event == "left")
            .order_by(PresenceEvent.at.desc())
        )
        return result.scalars().first()

    async def retrieve_last_join(self, mac: str) -> PresenceEvent | None:
        result = await self.session.execute(
            select(PresenceEvent)
            .where(PresenceEvent.mac == mac, PresenceEvent.event == "joined")
            .order_by(PresenceEvent.at.desc())
        )
        return result.scalars().first()

    async def list_since(self, moment: datetime) -> list[PresenceEvent]:
        result = await self.session.execute(
            select(PresenceEvent).where(PresenceEvent.at >= moment).order_by(PresenceEvent.at)
        )
        return list(result.scalars().all())

    async def delete_before(self, moment: datetime) -> None:
        result = await self.session.execute(select(PresenceEvent).where(PresenceEvent.at < moment))
        for event in result.scalars().all():
            await self.session.delete(event)
