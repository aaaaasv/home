"""The card that says a red alert has begun, and the same card written over once it is lifted."""
import logging
from collections.abc import Callable
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.bot.handlers.air_alert.formatting import render_alert_lowered, render_alert_raised
from src.bot.handlers.air_alert.keyboards import build_alert_keyboard
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import AIR_ALERT_CARD_KIND, PostedMessageTracker
from src.common.household_calendar import HouseholdCalendar
from src.common.time import as_utc
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_alert.domain import AirAlert, AlertTransition

logger = logging.getLogger(__name__)


class AlertAnnouncement:
    """
    One card per red alert: pinged once when it goes up, written over in place when it comes down.

    it earns its ping, and its own topic, because of what happened on 13.10: the strip on the switchboard
    came up before the siren was audible and before any channel had posted about it. the feed this bot
    already watches is the fastest thing in the flat, and until now the only thing it told was a light
    nobody was looking at.

    only red. the yellow drone warning runs for hours several nights a week — sixty-five of them in a
    fortnight against seven reds — and a topic that speaks for every one of them gets muted, after which
    it is silent on the night it matters.

    the card's message id and the minute it was raised are kept in the posted-messages table rather than in
    memory: an alert outlives a deploy, and after one the card still has to be findable to be written over
    and the span on it still has to be counted from the same minute.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        alert_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        household_calendar: HouseholdCalendar,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.alert_topic = alert_topic
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar
        self.tracker = PostedMessageTracker(bot=bot, uow_factory=uow_factory)

    async def handle(self, transition: AlertTransition, alert: AirAlert | None, strip_is_up: bool = False) -> None:
        if transition is AlertTransition.RAISED:
            await self._raise(alert, strip_is_up)
        elif transition is AlertTransition.CLEARED:
            await self._lower(alert)

    async def _raise(self, alert: AirAlert | None, strip_is_up: bool) -> None:
        raised_at = self.household_calendar.now()
        # forgotten rather than cleared: an earlier card is the record of an earlier alert and stays where it is
        await self.tracker.forget(AIR_ALERT_CARD_KIND)
        card = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.alert_topic.resolve(),
            text=render_alert_raised(alert, raised_at, self.household_calendar),
            # the button only appears when the strip is standing by our hand: offering to put out a light
            # somebody set themselves is how an automation earns its reputation
            reply_markup=build_alert_keyboard() if strip_is_up else None,
            # the one push in this house that has to arrive before the siren is audible
            disable_notification=False,
        )
        await self.tracker.remember(AIR_ALERT_CARD_KIND, card, reference=raised_at.isoformat())
        logger.info("Announced a red alert (%s)", alert.reason if alert is not None else "без причини")

    async def _lower(self, alert: AirAlert | None) -> None:
        """Written over where it stands — a second push to say the red is off is how a topic gets muted."""
        card = await self._remembered_card()
        if card is None:
            # the red began before this process did, so there is no card of ours to write over
            logger.info("The red alert is over, but no card of ours is standing to say so")
            return

        message_id, raised_at = card
        await self.tracker.forget(AIR_ALERT_CARD_KIND)
        text = render_alert_lowered(alert, raised_at, self.household_calendar.now(), self.household_calendar)
        try:
            # no keyboard: telegram drops the one that was there, which is what the button deserves by now
            await self.bot.edit_message_text(chat_id=self.chat_id, message_id=message_id, text=text)
        except TelegramBadRequest as error:
            logger.info("Could not write over the alert card: %s", error)
            return
        logger.info("The red alert is over; its card now says what is left")

    async def _remembered_card(self) -> tuple[int, datetime] | None:
        async with self.uow_factory() as uow:
            posted = await uow.posted_messages.list_by_kind(AIR_ALERT_CARD_KIND)
        if not posted or not posted[-1].reference:
            return None
        return posted[-1].message_id, as_utc(datetime.fromisoformat(posted[-1].reference))
