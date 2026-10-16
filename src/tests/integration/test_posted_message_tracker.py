from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage

from src.bot.services.posted_message_tracker import CARE_DIGEST_KIND, PostedMessageTracker
from src.infrastructure.db.uow import UnitOfWork
from src.tests.fakes import RecordingBot
from src.tests.integration.base import BaseIntegrationTestCase

CHAT_ID = -1001234567890
TOO_OLD = "Bad Request: message can't be deleted for everyone"
ALREADY_GONE = "Bad Request: message to delete not found"


class RefusingBot(RecordingBot):
    """A bot whose deletes come back refused, with the reason telegram actually gives."""

    def __init__(self, reason: str):
        super().__init__()
        self.reason = reason
        self.markup_taken_off: list[int] = []

    async def delete_message(self, chat_id, message_id):
        raise TelegramBadRequest(method=DeleteMessage(chat_id=chat_id, message_id=message_id), message=self.reason)

    async def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None):
        self.markup_taken_off.append(message_id)


class PostedMessageTrackerTestCase(BaseIntegrationTestCase):
    """
    What happens to a card the bot can no longer take away.

    the two limits are different lengths, measured 16.10.2026: an edit went through on a message 61 days
    old, a delete was refused past two days. so a lane that is cleared late leaves the card standing for
    good — message 567 in the family group is one — and the least it can do is stop holding buttons.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    async def remember(self, bot, message_id: int = 777) -> PostedMessageTracker:
        tracker = PostedMessageTracker(bot=bot, uow_factory=self.uow_factory)
        await tracker.remember(
            CARE_DIGEST_KIND, SimpleNamespace(message_id=message_id, chat=SimpleNamespace(id=CHAT_ID))
        )
        return tracker

    async def lane(self) -> list[int]:
        async with self.uow_factory() as uow:
            return [posted.message_id for posted in await uow.posted_messages.list_by_kind(CARE_DIGEST_KIND)]

    async def test_clear_a_card_too_old_to_delete_takes_its_buttons_off_instead(self):
        bot = RefusingBot(TOO_OLD)
        tracker = await self.remember(bot)

        await tracker.clear(CARE_DIGEST_KIND)

        self.assertEqual((bot.markup_taken_off, await self.lane()), ([777], []))

    async def test_clear_a_card_that_is_already_gone_asks_telegram_for_nothing_more(self):
        bot = RefusingBot(ALREADY_GONE)
        tracker = await self.remember(bot)

        await tracker.clear(CARE_DIGEST_KIND)

        self.assertEqual((bot.markup_taken_off, await self.lane()), ([], []))

    async def test_clear_a_card_telegram_deletes_never_touches_its_markup(self):
        bot = RecordingBot()
        tracker = await self.remember(bot)

        await tracker.clear(CARE_DIGEST_KIND)

        self.assertEqual((bot.deleted, await self.lane()), ([777], []))
