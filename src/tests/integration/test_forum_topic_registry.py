from src.bot.handlers.plants import PLANTS_MODULE_NAME
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.infrastructure.db.uow import UnitOfWork
from src.tests.fakes import FakeForumBot
from src.tests.integration.base import BaseIntegrationTestCase

CHAT_ID = -1001234567890


class ForumTopicRegistryTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.bot = FakeForumBot()

    def build_registry(self, chat_id: int = CHAT_ID, configured_topic_id: int | None = None) -> ForumTopicRegistry:
        return ForumTopicRegistry(
            bot=self.bot,
            chat_id=chat_id,
            module_name=PLANTS_MODULE_NAME,
            title="🪴 Рослини",
            configured_topic_id=configured_topic_id,
            uow_factory=lambda: UnitOfWork(session_factory=self.session_factory),
        )

    async def retrieve_remembered_topic_id(self) -> int | None:
        async with self.uow as uow:
            topic = await uow.forum_topics.retrieve_by_module_name(PLANTS_MODULE_NAME)
            return None if topic is None else topic.message_thread_id

    async def test_resolve_in_a_chat_without_topics_returns_none(self):
        self.bot.is_forum = False

        topic_id = await self.build_registry().resolve()

        self.assertIsNone(topic_id)
        self.assertEqual(self.bot.created_topic_names, [])

    async def test_resolve_without_a_remembered_topic_creates_one_and_remembers_it(self):
        topic_id = await self.build_registry().resolve()

        self.assertEqual(topic_id, 100)
        self.assertEqual(self.bot.created_topic_names, ["🪴 Рослини"])
        self.assertEqual(await self.retrieve_remembered_topic_id(), 100)

    async def test_resolve_with_a_remembered_topic_reuses_it_without_creating_another(self):
        await self.build_registry().resolve()

        topic_id = await self.build_registry().resolve()

        self.assertEqual(topic_id, 100)
        self.assertEqual(self.bot.created_topic_names, ["🪴 Рослини"])

    async def test_resolve_with_a_configured_topic_id_adopts_it_without_creating_another(self):
        topic_id = await self.build_registry(configured_topic_id=42).resolve()

        self.assertEqual(topic_id, 42)
        self.assertEqual(self.bot.created_topic_names, [])
        self.assertEqual(await self.retrieve_remembered_topic_id(), 42)

    async def test_resolve_in_a_different_chat_creates_a_new_topic(self):
        await self.build_registry().resolve()

        topic_id = await self.build_registry(chat_id=-1009999999999).resolve()

        self.assertEqual(topic_id, 101)
        self.assertEqual(self.bot.created_topic_names, ["🪴 Рослини", "🪴 Рослини"])
        self.assertEqual(await self.retrieve_remembered_topic_id(), 101)

    async def test_create_after_the_topic_was_deleted_replaces_the_remembered_one(self):
        registry = self.build_registry()
        await registry.resolve()

        topic_id = await registry.create()

        self.assertEqual(topic_id, 101)
        self.assertEqual(await self.retrieve_remembered_topic_id(), 101)
