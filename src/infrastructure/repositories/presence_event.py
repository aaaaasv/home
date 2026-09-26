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

    async def retrieve_last_event(self, mac: str) -> PresenceEvent | None:
        """The last thing this phone did, whichever way — which is how a resident is told from a companion."""
        result = await self.session.execute(
            select(PresenceEvent).where(PresenceEvent.mac == mac).order_by(PresenceEvent.at.desc())
        )
        return result.scalars().first()

    async def list_macs(self) -> list[str]:
        """Every address the log knows — by construction only the family's phones are ever written here."""
        result = await self.session.execute(select(PresenceEvent.mac).distinct())
        return list(result.scalars().all())

    async def retrieve_last_event_before(self, mac: str, moment: datetime) -> PresenceEvent | None:
        """What this phone was doing when the window opened, which decides whether it starts out at home."""
        result = await self.session.execute(
            select(PresenceEvent)
            .where(PresenceEvent.mac == mac, PresenceEvent.at < moment)
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
