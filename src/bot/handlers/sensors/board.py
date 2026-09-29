from collections.abc import Callable

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from src.bot.handlers.sensors.contents import ClimateCardContents
from src.bot.handlers.sensors.formatting import render_climate_card
from src.bot.handlers.sensors.keyboards import build_climate_card_keyboard
from src.bot.services.single_message_board import SingleMessageBoard
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork

CLIMATE_CARD_KIND = "climate_card"


class ThreadTopic:
    """The topic a command was typed in — the card is only ever asked for from inside it."""

    def __init__(self, topic_id: int | None):
        self.topic_id = topic_id


class ClimateCardBoard(SingleMessageBoard):
    """
    The /climate card as one message: /climate moves it to the bottom of the topic, 🔄 edits it where it stands.

    it is a board rather than the weather digest's shape because nothing schedules it. the digest posts itself
    every morning and needs a job, a forecast provider and a composition-root wiring; this card is a pull, and
    the shared board already does exactly that — remember one message, edit it, delete the one it replaces.
    """

    kind = CLIMATE_CARD_KIND

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        topic_id: int | None,
        uow_factory: Callable[[], UnitOfWork],
        household_calendar: HouseholdCalendar,
    ):
        super().__init__(bot=bot, chat_id=chat_id, forum_topic=ThreadTopic(topic_id), uow_factory=uow_factory)
        self.household_calendar = household_calendar

    def render(self, contents: ClimateCardContents) -> str:
        return render_climate_card(contents, self.household_calendar)

    def build_keyboard(self, contents: ClimateCardContents) -> InlineKeyboardMarkup:
        return build_climate_card_keyboard()

    async def refresh_message(self, message_id: int, contents: ClimateCardContents) -> None:
        """Edit the very card whose button was pressed, so a copy that could not be deleted still stops lying."""
        if not await self._edit(message_id, contents):
            await self.repost(contents)
