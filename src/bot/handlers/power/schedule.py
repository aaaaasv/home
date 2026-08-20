import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from src.bot.handlers.power.keyboards import OutageScheduleCallback
from src.bot.handlers.power.messages import POWER_SCHEDULE_REFRESHING
from src.bot.handlers.power.outage_schedule_board import OutageScheduleBoard

logger = logging.getLogger(__name__)

router = Router(name="outage_schedule")


@router.callback_query(OutageScheduleCallback.filter())
async def refresh_outage_schedule(
    callback: CallbackQuery,
    outage_schedule_board: OutageScheduleBoard | None = None,
) -> None:
    # a status banner up front while the schedule is re-fetched; the refreshed board itself is the result
    await callback.answer(POWER_SCHEDULE_REFRESHING)
    # the button rides on a board that only exists when yasno is enabled, but a stale one may outlive a disable
    if outage_schedule_board is not None:
        await outage_schedule_board.refresh()
