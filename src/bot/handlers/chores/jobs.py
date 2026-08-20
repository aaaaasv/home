"""The scheduled job that keeps one card per deadline alive until the chore is done."""
import logging
from collections.abc import Callable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.bot.handlers.chores.formatting import render_chore_deadline_card
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import CHORE_DEADLINE_KIND, PostedMessageTracker
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.chores.domain import ChoreReminder
from src.modules.chores.use_cases.evaluate_chore_deadlines import EvaluateChoreDeadlinesUseCase

logger = logging.getLogger(__name__)


class ChoreDeadlineJob:
    """
    Keeps one standing card per chore whose deadline is near, and stays silent the rest of the time.

    a chore with no deadline never appears here; one still far out never appears. the card is posted with a ping
    the moment a deadline enters its lead window, rewritten silently as the day turns («завтра»→«сьогодні»→
    «прострочено»), and deleted the instant the chore is done — so a family with nothing due soon sees nothing.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        chores_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        household_calendar: HouseholdCalendar,
        settings: Settings,
        posted_message_tracker: PostedMessageTracker,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.chores_topic = chores_topic
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar
        self.settings = settings
        self.posted_message_tracker = posted_message_tracker

    async def __call__(self) -> None:
        reminders = await EvaluateChoreDeadlinesUseCase(
            uow=self.uow_factory(),
            today=self.household_calendar.today(),
            lead_days=self.settings.CHORE_REMINDER_LEAD_DAYS,
        )()
        desired = {reminder.chore_id: reminder for reminder in reminders}

        async with self.uow_factory() as uow:
            carded = {
                int(posted.reference): posted.message_id
                for posted in await uow.posted_messages.list_by_kind(CHORE_DEADLINE_KIND)
            }

        topic_id = await self.chores_topic.resolve()
        for chore_id, reminder in desired.items():
            if chore_id in carded:
                await self._rewrite_card(carded[chore_id], reminder, topic_id)
            else:
                await self._post_card(reminder, topic_id)

        # a chore whose deadline was pushed back out of the window (or that vanished) must not keep a card
        for stale_chore_id in carded.keys() - desired.keys():
            await self.posted_message_tracker.clear_one(CHORE_DEADLINE_KIND, str(stale_chore_id))

    async def _post_card(self, reminder: ChoreReminder, topic_id: int | None) -> None:
        # a deadline crossing into its lead window is the one moment worth a ping
        posted = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=topic_id,
            text=render_chore_deadline_card(reminder),
            disable_notification=False,
        )
        await self.posted_message_tracker.remember(CHORE_DEADLINE_KIND, posted, reference=str(reminder.chore_id))
        logger.info("Posted a deadline card for chore %s", reminder.chore_id)

    async def _rewrite_card(self, message_id: int, reminder: ChoreReminder, topic_id: int | None) -> None:
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id, message_id=message_id, text=render_chore_deadline_card(reminder)
            )
            return
        except TelegramBadRequest as error:
            # unchanged text needs no rewrite; anything else (gone, older than 48h) falls back to a fresh card
            if "message is not modified" in str(error).lower():
                return

        await self.posted_message_tracker.clear_one(CHORE_DEADLINE_KIND, str(reminder.chore_id))
        posted = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=topic_id,
            text=render_chore_deadline_card(reminder),
            # a silent repost of a card that was already there — not a fresh crossing, so no ping
            disable_notification=True,
        )
        await self.posted_message_tracker.remember(CHORE_DEADLINE_KIND, posted, reference=str(reminder.chore_id))
