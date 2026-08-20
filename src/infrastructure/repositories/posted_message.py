from sqlalchemy import delete, select

from src.infrastructure.db.models import PostedMessage
from src.infrastructure.repositories.base import SQLAlchemyRepository


class PostedMessageRepository(SQLAlchemyRepository[PostedMessage]):
    model = PostedMessage

    async def list_by_kind(self, kind: str) -> list[PostedMessage]:
        result = await self.session.execute(select(PostedMessage).where(PostedMessage.kind == kind))
        return list(result.scalars().all())

    async def delete_by_kind(self, kind: str) -> None:
        await self.session.execute(delete(PostedMessage).where(PostedMessage.kind == kind))

    async def list_by_reference(self, kind: str, reference: str) -> list[PostedMessage]:
        result = await self.session.execute(
            select(PostedMessage).where(PostedMessage.kind == kind, PostedMessage.reference == reference)
        )
        return list(result.scalars().all())

    async def delete_by_reference(self, kind: str, reference: str, keep_message_id: int | None = None) -> None:
        statement = delete(PostedMessage).where(PostedMessage.kind == kind, PostedMessage.reference == reference)
        if keep_message_id is not None:
            statement = statement.where(PostedMessage.message_id != keep_message_id)
        await self.session.execute(statement)

    async def retrieve_latest_by_kind(self, kind: str, chat_id: int) -> PostedMessage | None:
        """The one message a self-editing board lives in — its lane holds a single row per chat."""
        result = await self.session.execute(
            select(PostedMessage)
            .where(PostedMessage.kind == kind, PostedMessage.chat_id == chat_id)
            .order_by(PostedMessage.id.desc())
        )
        return result.scalars().first()
