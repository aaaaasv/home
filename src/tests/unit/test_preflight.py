import unittest

from aiogram.exceptions import TelegramMigrateToChat
from aiogram.methods import GetChatMemberCount
from aiogram.types import Chat

from src.bot.preflight import ChatIsUnusableError, verify_reminder_chat

CHAT_ID = -5150799557
MIGRATED_CHAT_ID = -1004385845232


class FakeChatBot:
    def __init__(self, is_forum: bool = True, migrate_to_chat_id: int | None = None):
        self.is_forum = is_forum
        self.migrate_to_chat_id = migrate_to_chat_id

    async def get_chat_member_count(self, chat_id: int) -> int:
        if self.migrate_to_chat_id is not None:
            raise TelegramMigrateToChat(
                method=GetChatMemberCount(chat_id=chat_id),
                message="group chat was upgraded to a supergroup chat",
                migrate_to_chat_id=self.migrate_to_chat_id,
            )
        return 4

    async def get_chat(self, chat_id: int) -> Chat:
        return Chat(id=chat_id, type="supergroup", title="хоум", is_forum=self.is_forum)


class VerifyReminderChatTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_verify_reminder_chat_of_a_forum_passes(self):
        bot = FakeChatBot()

        await verify_reminder_chat(bot, CHAT_ID)

    async def test_verify_reminder_chat_that_was_upgraded_names_the_new_chat_id(self):
        bot = FakeChatBot(migrate_to_chat_id=MIGRATED_CHAT_ID)

        with self.assertRaises(ChatIsUnusableError) as context:
            await verify_reminder_chat(bot, CHAT_ID)

        self.assertEqual(
            str(context.exception),
            f"Chat {CHAT_ID} was upgraded to a supergroup and its id changed — enabling topics does this. "
            f"Set TELEGRAM_REMINDER_CHAT_ID={MIGRATED_CHAT_ID} in .env, then "
            f"`docker compose up -d --force-recreate` (a plain restart does not reload .env).",
        )

    async def test_verify_reminder_chat_without_topics_refuses_to_start(self):
        bot = FakeChatBot(is_forum=False)

        with self.assertRaises(ChatIsUnusableError) as context:
            await verify_reminder_chat(bot, CHAT_ID)

        self.assertEqual(
            str(context.exception),
            f"Chat {CHAT_ID} ('хоум') has no topics enabled, so every module would answer nothing. "
            f"Turn Topics on in the group settings.",
        )
