"""Answering the one question about the grid that no sensor in the flat can answer."""
import logging
from collections.abc import Callable

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from src.bot.handlers.power.keyboards import SupplyCallback, build_supply_keyboard
from src.bot.handlers.power.messages import (
    POWER_SUPPLY_BACK_ON_GRID,
    POWER_SUPPLY_ON_STATION,
    POWER_SUPPLY_TOAST_GRID,
    POWER_SUPPLY_TOAST_STATION,
)
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import DeclaredSupply
from src.modules.power.use_cases.declare_supply import DeclareSupplyUseCase

logger = logging.getLogger(__name__)

router = Router(name="supply")


@router.callback_query(SupplyCallback.filter())
async def declare_supply(
    callback: CallbackQuery,
    callback_data: SupplyCallback,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    """
    Write down what is feeding the pi's socket, and rewrite the card that asked in place.

    the card is rewritten rather than answered beside, because it is the thing standing in the topic being
    read: «світло є» left above a correction is the version somebody scrolling past will believe. saying
    the grid is back is left to the mains watch, which owns that sentence and knows the whole span.
    """
    retracted = await DeclareSupplyUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        callback_data.supply, retract_grid_event_id=callback_data.retract or None
    )
    on_station = callback_data.supply is DeclaredSupply.STATION
    await _answer_quietly(callback, POWER_SUPPLY_TOAST_STATION if on_station else POWER_SUPPLY_TOAST_GRID)
    logger.info("The supply was declared %s, retracted announcement: %s", callback_data.supply.value, retracted)

    await _rewrite(callback, callback_data.supply, callback_data.confirming)


async def _rewrite(callback: CallbackQuery, supply: DeclaredSupply, confirming: bool) -> None:
    if supply is DeclaredSupply.STATION:
        text, keyboard = POWER_SUPPLY_ON_STATION, build_supply_keyboard(supply)
    elif confirming:
        # «так, мережа» agrees with what the card already says: keep its first paragraph, which holds the span
        # nobody can look up afterwards, and drop the question under it
        text, keyboard = _first_paragraph(callback), None
    else:
        text, keyboard = POWER_SUPPLY_BACK_ON_GRID, None

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        # a bot may edit its own message for 48 hours only; the declaration is written either way
        if "message is not modified" not in str(error):
            logger.info("The supply card could not be rewritten: %s", error)


def _first_paragraph(callback: CallbackQuery) -> str:
    return (callback.message.html_text or "").split("\n\n")[0]


async def _answer_quietly(callback: CallbackQuery, text: str) -> None:
    try:
        await callback.answer(text)
    except TelegramBadRequest:
        pass
