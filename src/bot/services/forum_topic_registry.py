import logging
from collections.abc import Callable

from aiogram import Bot

from src.infrastructure.db.uow import UnitOfWork

logger = logging.getLogger(__name__)


class ForumTopicRegistry:
    """Keeps a module's forum topic alive: the bot api cannot list topics, so the bot remembers the one it created"""

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        module_name: str,
        title: str,
        configured_topic_id: int | None,
        uow_factory: Callable[[], UnitOfWork],
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.module_name = module_name
        self.title = title
        self.configured_topic_id = configured_topic_id
        self.uow_factory = uow_factory
        # handlers are filtered by topic on every update, so the resolved id is kept in memory
        self.topic_id: int | None = None
        self.is_resolved = False

    async def resolve(self) -> int | None:
        if not self.is_resolved:
            self.topic_id = await self._resolve_topic_id()
            self.is_resolved = True
        return self.topic_id

    async def create(self) -> int:
        topic = await self.bot.create_forum_topic(chat_id=self.chat_id, name=self.title)
        await self._remember_topic_id(topic.message_thread_id)
        self.topic_id = topic.message_thread_id
        self.is_resolved = True
        logger.info("Created the forum topic '%s' (%s)", self.title, topic.message_thread_id)
        return topic.message_thread_id

    async def _resolve_topic_id(self) -> int | None:
        if not await self._chat_is_a_forum():
            return None

        remembered_topic_id = await self._retrieve_remembered_topic_id()
        if remembered_topic_id is not None:
            return remembered_topic_id

        if self.configured_topic_id is not None:
            await self._remember_topic_id(self.configured_topic_id)
            return self.configured_topic_id

        return await self.create()

    async def _chat_is_a_forum(self) -> bool:
        chat = await self.bot.get_chat(self.chat_id)
        return bool(chat.is_forum)

    async def _retrieve_remembered_topic_id(self) -> int | None:
        async with self.uow_factory() as uow:
            topic = await uow.forum_topics.retrieve_by_module_name(self.module_name)
            if topic is None or topic.chat_id != self.chat_id:
                return None
            return topic.message_thread_id

    async def _remember_topic_id(self, message_thread_id: int) -> None:
        async with self.uow_factory() as uow:
            topic = await uow.forum_topics.retrieve_by_module_name(self.module_name)
            if topic is None:
                await uow.forum_topics.create(
                    {
                        "module_name": self.module_name,
                        "chat_id": self.chat_id,
                        "message_thread_id": message_thread_id,
                    }
                )
                return

            await uow.forum_topics.update(topic.id, {"chat_id": self.chat_id, "message_thread_id": message_thread_id})
