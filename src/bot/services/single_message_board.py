import logging
from collections.abc import Callable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.infrastructure.db.uow import UnitOfWork

logger = logging.getLogger(__name__)

# a bot may edit its own message for 48 hours, after which telegram refuses and the list must be reposted.
# "message is not modified" is deliberately absent: it means the message already says the right thing, which
# is success. treating it as uneditable made every no-op refresh delete the board and repost it at the
# bottom of the topic — visible to the family as the list jumping for no reason
UNEDITABLE_MESSAGE_ERRORS = ("message can't be edited", "message to edit not found", "message_id_invalid")


class SingleMessageBoard:
    """
    One list living in one message: edited in place while Telegram allows it, reposted once it does not.

    subclasses supply a kind, a renderer and a keyboard builder — everything else is identical, which is why
    the shopping, places and chores boards used to be three copies of the same ninety lines.
    """

    kind: str

    def render(self, contents) -> str:
        raise NotImplementedError

    def build_keyboard(self, contents) -> InlineKeyboardMarkup:
        raise NotImplementedError

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        forum_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.forum_topic = forum_topic
        self.uow_factory = uow_factory

    async def refresh(self, contents) -> None:
        """Edit the list where it stands — no new message, no notification — and repost only once editing expires."""
        message_id = await self._retrieve_remembered_message_id()
        if message_id is not None and await self._edit(message_id, contents):
            return

        await self.repost(contents)

    async def repost(self, contents) -> None:
        """On /list — move the list to the bottom of the topic, where the person is already looking."""
        previous_message_id = await self._retrieve_remembered_message_id()

        message = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=self.forum_topic.topic_id,
            text=self.render(contents),
            reply_markup=self.build_keyboard(contents),
        )
        await self._remember_message_id(message.message_id)

        if previous_message_id is not None:
            await self._delete(previous_message_id)

    async def _edit(self, message_id: int, contents) -> bool:
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=message_id,
                text=self.render(contents),
                reply_markup=self.build_keyboard(contents),
            )
        except TelegramBadRequest as error:
            reason = error.message.lower()
            if "message is not modified" in reason:
                return True
            if not any(uneditable in reason for uneditable in UNEDITABLE_MESSAGE_ERRORS):
                raise
            logger.info("The %s board message %s is no longer editable, reposting it", self.kind, message_id)
            return False
        return True

    async def _delete(self, message_id: int) -> None:
        try:
            await self.bot.delete_message(chat_id=self.chat_id, message_id=message_id)
        except TelegramBadRequest:
            # a message the family already deleted, or one too old for the bot to delete — the new list is up anyway
            logger.info("Could not delete the previous %s board message %s", self.kind, message_id)

    async def _retrieve_remembered_message_id(self) -> int | None:
        async with self.uow_factory() as uow:
            posted = await uow.posted_messages.retrieve_latest_by_kind(self.kind, self.chat_id)
            return None if posted is None else posted.message_id

    async def _remember_message_id(self, message_id: int) -> None:
        async with self.uow_factory() as uow:
            posted = await uow.posted_messages.retrieve_latest_by_kind(self.kind, self.chat_id)
            if posted is None:
                await uow.posted_messages.create(
                    {"kind": self.kind, "chat_id": self.chat_id, "message_id": message_id, "reference": None}
                )
                return

            await uow.posted_messages.update(posted.id, {"message_id": message_id})
