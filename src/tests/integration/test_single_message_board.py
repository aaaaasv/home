from aiogram.exceptions import TelegramBadRequest

from src.bot.services.single_message_board import SingleMessageBoard
from src.infrastructure.db.uow import UnitOfWork
from src.tests.fakes import StubForumTopic
from src.tests.integration.base import BaseIntegrationTestCase

CHAT_ID = -1001234567890


class FakeRequest:
    def __init__(self, method: str):
        self.method = method


class RecordingBoardBot:
    """Counts what the board asked Telegram to do, and can be told to fail one edit the way Telegram would."""

    def __init__(self, edit_error: str | None = None):
        self.edit_error = edit_error
        self.sent: list[str] = []
        self.edited: list[int] = []
        self.deleted: list[int] = []

    async def send_message(self, chat_id, message_thread_id, text, reply_markup):
        self.sent.append(text)

        class Sent:
            message_id = 500 + len(self.sent)

        return Sent()

    async def edit_message_text(self, chat_id, message_id, text, reply_markup):
        self.edited.append(message_id)
        if self.edit_error is not None:
            raise TelegramBadRequest(method=FakeRequest("editMessageText"), message=self.edit_error)

    async def delete_message(self, chat_id, message_id):
        self.deleted.append(message_id)


class ListBoard(SingleMessageBoard):
    kind = "test_list"

    def render(self, contents) -> str:
        return contents

    def build_keyboard(self, contents):
        return None


class SingleMessageBoardTestCase(BaseIntegrationTestCase):
    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_board(self, bot) -> ListBoard:
        return ListBoard(bot=bot, chat_id=CHAT_ID, forum_topic=StubForumTopic(), uow_factory=self.uow_factory)

    async def remembered_message_id(self) -> int | None:
        async with self.uow_factory() as uow:
            posted = await uow.posted_messages.retrieve_latest_by_kind("test_list", CHAT_ID)
            return None if posted is None else posted.message_id

    async def test_refresh_with_no_remembered_message_posts_a_new_one(self):
        bot = RecordingBoardBot()

        await self.build_board(bot).refresh("список")

        self.assertEqual(bot.sent, ["список"])
        self.assertEqual(bot.edited, [])
        self.assertEqual(await self.remembered_message_id(), 501)

    async def test_refresh_edits_the_remembered_message_in_place(self):
        bot = RecordingBoardBot()
        board = self.build_board(bot)
        await board.refresh("перший")

        await board.refresh("другий")

        self.assertEqual(bot.sent, ["перший"])
        self.assertEqual(bot.edited, [501])
        self.assertEqual(bot.deleted, [])

    async def test_refresh_when_the_text_is_unchanged_keeps_the_message_and_does_not_repost(self):
        bot = RecordingBoardBot()
        board = self.build_board(bot)
        await board.refresh("олія")
        bot.edit_error = "Bad Request: message is not modified"

        await board.refresh("олія")

        self.assertEqual(bot.sent, ["олія"])
        self.assertEqual(bot.deleted, [])
        self.assertEqual(await self.remembered_message_id(), 501)

    async def test_refresh_after_the_edit_window_expires_reposts_and_deletes_the_old_message(self):
        bot = RecordingBoardBot()
        board = self.build_board(bot)
        await board.refresh("перший")
        bot.edit_error = "Bad Request: message can't be edited"

        await board.refresh("другий")

        self.assertEqual(bot.sent, ["перший", "другий"])
        self.assertEqual(bot.deleted, [501])
        self.assertEqual(await self.remembered_message_id(), 502)

    async def test_refresh_raises_when_telegram_rejects_the_edit_for_an_unknown_reason(self):
        bot = RecordingBoardBot()
        board = self.build_board(bot)
        await board.refresh("перший")
        bot.edit_error = "Bad Request: chat not found"

        with self.assertRaises(TelegramBadRequest) as context:
            await board.refresh("другий")

        self.assertEqual(str(context.exception), "Telegram server says - Bad Request: chat not found")
