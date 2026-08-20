import unittest
from datetime import datetime, timezone

from aiogram.types import CallbackQuery, Chat, InaccessibleMessage, Message, User

from src.bot.filters import HasAccessibleMessage, InModuleTopic
from src.bot.handlers.plants import PLANTS_MODULE_NAME
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.tests.fakes import FakeForumBot

CHAT_ID = -1001234567890
PLANTS_TOPIC_ID = 100
MOMENT = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)


def build_message(chat_type: str = "supergroup", message_thread_id: int | None = None) -> Message:
    return Message(
        message_id=1,
        date=MOMENT,
        chat=Chat(id=CHAT_ID, type=chat_type, is_forum=True),
        message_thread_id=message_thread_id,
    )


def build_callback_query(message: Message | InaccessibleMessage) -> CallbackQuery:
    return CallbackQuery(
        id="1",
        from_user=User(id=7, is_bot=False, first_name="Богдан"),
        chat_instance="chat-instance",
        message=message,
        data="care:1:watering:0",
    )


class InModuleTopicTestCase(unittest.IsolatedAsyncioTestCase):
    def build_filter(self, topic_id: int | None = PLANTS_TOPIC_ID) -> InModuleTopic:
        registry = ForumTopicRegistry(
            bot=FakeForumBot(),
            chat_id=CHAT_ID,
            module_name=PLANTS_MODULE_NAME,
            title="🪴 Рослини",
            configured_topic_id=None,
            uow_factory=None,
        )
        registry.topic_id = topic_id
        registry.is_resolved = True
        return InModuleTopic(registry)

    async def test_in_module_topic_inside_the_topic_passes(self):
        message = build_message(message_thread_id=PLANTS_TOPIC_ID)

        passes = await self.build_filter()(message)

        self.assertTrue(passes)

    async def test_in_module_topic_in_the_general_topic_is_rejected(self):
        message = build_message(message_thread_id=None)

        passes = await self.build_filter()(message)

        self.assertFalse(passes)

    async def test_in_module_topic_in_another_topic_is_rejected(self):
        message = build_message(message_thread_id=999)

        passes = await self.build_filter()(message)

        self.assertFalse(passes)

    async def test_in_module_topic_in_a_private_chat_is_rejected(self):
        message = build_message(chat_type="private")

        passes = await self.build_filter()(message)

        self.assertFalse(passes)

    async def test_in_module_topic_without_a_resolved_topic_is_rejected(self):
        message = build_message(message_thread_id=None)

        passes = await self.build_filter(topic_id=None)(message)

        self.assertFalse(passes)


class HasAccessibleMessageTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_has_accessible_message_of_a_button_in_any_topic_passes(self):
        callback = build_callback_query(build_message(message_thread_id=999))

        passes = await HasAccessibleMessage()(callback)

        self.assertTrue(passes)

    async def test_has_accessible_message_of_a_button_in_the_general_topic_passes(self):
        callback = build_callback_query(build_message(message_thread_id=None))

        passes = await HasAccessibleMessage()(callback)

        self.assertTrue(passes)

    async def test_has_accessible_message_of_an_unreachable_message_is_rejected(self):
        # telegram stamps an inaccessible message with date 0 and drops every other field
        callback = build_callback_query(
            InaccessibleMessage(message_id=1, date=0, chat=Chat(id=CHAT_ID, type="supergroup", is_forum=True))
        )

        passes = await HasAccessibleMessage()(callback)

        self.assertFalse(passes)
