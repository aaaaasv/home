from datetime import datetime

from sqlalchemy import select

from src.infrastructure.db.models import AirThreatNotice
from src.infrastructure.repositories.base import SQLAlchemyRepository


class AirThreatNoticeRepository(SQLAlchemyRepository[AirThreatNotice]):
    model = AirThreatNotice

    async def list_open(self) -> list[AirThreatNotice]:
        result = await self.session.execute(select(AirThreatNotice).where(AirThreatNotice.closed_at.is_(None)))
        return list(result.scalars().all())

    async def retrieve_by_tracker(self, tracker_id: str) -> AirThreatNotice | None:
        result = await self.session.execute(select(AirThreatNotice).where(AirThreatNotice.tracker_id == tracker_id))
        return result.scalars().first()

    async def open_notice(self, tracker_id: str, moment: datetime) -> None:
        """A track seen again after it faded reopens its own row rather than starting a second one."""
        existing = await self.retrieve_by_tracker(tracker_id)
        if existing is None:
            self.session.add(AirThreatNotice(tracker_id=tracker_id, first_seen_at=moment, last_seen_at=moment))
            return
        existing.closed_at = None
        existing.last_seen_at = moment
        existing.message_id = None
        existing.rendered_text = None

    async def mark_seen(self, tracker_id: str, moment: datetime) -> None:
        existing = await self.retrieve_by_tracker(tracker_id)
        if existing is not None:
            existing.last_seen_at = moment

    async def close_notice(self, tracker_id: str, moment: datetime) -> None:
        existing = await self.retrieve_by_tracker(tracker_id)
        if existing is not None:
            existing.closed_at = moment

    async def attach_message(self, tracker_id: str, chat_id: int, message_id: int, rendered_text: str) -> None:
        existing = await self.retrieve_by_tracker(tracker_id)
        if existing is not None:
            existing.chat_id = chat_id
            existing.message_id = message_id
            existing.rendered_text = rendered_text

    async def delete_closed_before(self, moment: datetime) -> None:
        result = await self.session.execute(
            select(AirThreatNotice).where(AirThreatNotice.closed_at.is_not(None), AirThreatNotice.closed_at < moment)
        )
        for notice in result.scalars().all():
            await self.session.delete(notice)
