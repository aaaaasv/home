from sqlalchemy import select

from src.infrastructure.db.models import ForumTopic
from src.infrastructure.repositories.base import SQLAlchemyRepository


class ForumTopicRepository(SQLAlchemyRepository[ForumTopic]):
    model = ForumTopic

    async def retrieve_by_module_name(self, module_name: str) -> ForumTopic | None:
        result = await self.session.execute(select(ForumTopic).where(ForumTopic.module_name == module_name))
        return result.scalar_one_or_none()

    async def retrieve_by_thread_id(self, chat_id: int, message_thread_id: int) -> ForumTopic | None:
        result = await self.session.execute(
            select(ForumTopic).where(ForumTopic.chat_id == chat_id, ForumTopic.message_thread_id == message_thread_id)
        )
        return result.scalar_one_or_none()
