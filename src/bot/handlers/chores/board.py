from collections.abc import Callable

from aiogram import Bot

from src.bot.handlers.chores.formatting import render_chores_list
from src.bot.handlers.chores.keyboards import build_chores_list_keyboard
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import CHORES_LIST_KIND
from src.bot.services.single_message_board import SingleMessageBoard
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.chores.domain import ChoresList

CHORES_MODULE_NAME = "chores"


class ChoresBoard(SingleMessageBoard):
    """The single self-editing message the chores list lives in, reposted once Telegram's 48h window closes."""

    kind = CHORES_LIST_KIND

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        forum_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        household_calendar: HouseholdCalendar,
    ):
        super().__init__(bot, chat_id, forum_topic, uow_factory)
        # a deadline reads as «завтра» or «прострочено» only relative to the household's today
        self.household_calendar = household_calendar

    def render(self, chores: ChoresList) -> str:
        return render_chores_list(chores, self.household_calendar.today())

    def build_keyboard(self, chores: ChoresList):
        return build_chores_list_keyboard(chores)
