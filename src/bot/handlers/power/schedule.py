import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from src.bot.handlers.power.board import PowerBoard
from src.bot.handlers.power.keyboards import OutageScheduleCallback
from src.bot.handlers.power.messages import POWER_SCHEDULE_REFRESHING

logger = logging.getLogger(__name__)

router = Router(name="outage_schedule")


@router.callback_query(OutageScheduleCallback.filter())
async def refresh_the_power_board(callback: CallbackQuery, power_board: PowerBoard | None = None) -> None:
    # a status banner up front while the schedule is re-fetched; the refreshed board itself is the result
    await callback.answer(POWER_SCHEDULE_REFRESHING)
    # the button rides on a board that may outlive a disabled module, so a stale tap must find nothing to do
    if power_board is None:
        return

    # the one place that asks yasno on demand: «Оновити» means ask again, not redraw what we already had
    await power_board.read_outlook()
    await power_board.draw()
