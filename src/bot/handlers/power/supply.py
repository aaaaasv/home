"""Answering the one question about the grid that no sensor in the flat can answer."""
import logging
from collections.abc import Callable
from datetime import timedelta

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from src.bot.handlers.power.board import PowerBoard
from src.bot.handlers.power.keyboards import SupplyCallback, build_supply_keyboard
from src.bot.handlers.power.messages import (
    POWER_SUPPLY_BACK_ON_GRID,
    POWER_SUPPLY_ON_STATION,
    POWER_SUPPLY_TOAST_GRID,
    POWER_SUPPLY_TOAST_STATION,
    POWER_SUPPLY_TOAST_STATION_RETRACTED,
)
from src.common.household_calendar import HouseholdCalendar
from src.common.time import as_utc
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import DeclaredSupply, GridState
from src.modules.power.use_cases.declare_supply import DeclareSupplyUseCase

logger = logging.getLogger(__name__)

router = Router(name="supply")

# tapped on the board, «це не мережа» takes back a «світло є» this recent and no older: the board is
# always current, so a correction made on it is about something that has just happened
BOARD_RETRACTS_WITHIN = timedelta(hours=1)


@router.callback_query(SupplyCallback.filter())
async def declare_supply(
    callback: CallbackQuery,
    callback_data: SupplyCallback,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    power_board: PowerBoard | None = None,
) -> None:
    """
    Write down what is feeding the pi's socket, from whichever of the two places said so.

    **a push card and the board need opposite treatment.** the card that asked is rewritten in place,
    because it is the thing standing in the topic being read and «світло є» left above a correction is
    the version somebody scrolling past believes. the board must not be rewritten at all: it redraws
    itself from the state every minute, and the next refresh would undo anything written over it.

    saying that the grid is back is left to the mains watch, which owns that sentence and knows the span.
    """
    retract = callback_data.retract or None
    if callback_data.board and callback_data.supply is DeclaredSupply.STATION:
        retract = await _recent_restoration(uow_factory, household_calendar)

    retracted = await DeclareSupplyUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        callback_data.supply, retract_grid_event_id=retract
    )
    on_station = callback_data.supply is DeclaredSupply.STATION
    toast = POWER_SUPPLY_TOAST_STATION if on_station else POWER_SUPPLY_TOAST_GRID
    await _answer_quietly(callback, POWER_SUPPLY_TOAST_STATION_RETRACTED if retracted and on_station else toast)
    logger.info("The supply was declared %s, retracted announcement: %s", callback_data.supply.value, retracted)

    if callback_data.board:
        # the board owns its own text; it is redrawn so the heading, the line and the button all agree
        if power_board is not None:
            await power_board.draw()
        return
    await _rewrite(callback, callback_data.supply, callback_data.confirming)


async def _recent_restoration(
    uow_factory: Callable[[], UnitOfWork], household_calendar: HouseholdCalendar
) -> int | None:
    """
    The «світло є» this correction is about, if there is one recent enough to be the same event.

    the board carries no row id of its own — it is not a reply to a particular announcement — so it looks
    for one. only the newest row, only if it says the light came back, and only within the hour: older
    than that and the correction is about now rather than about that announcement, and deleting it would
    cut a hole in the middle of the journal every «скільки годин без світла» is counted from.
    """
    async with uow_factory() as uow:
        latest = await uow.grid_events.retrieve_latest()
    if latest is None or latest.state != GridState.ON_GRID.value:
        return None
    if household_calendar.now() - as_utc(latest.at) > BOARD_RETRACTS_WITHIN:
        return None
    return latest.id


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
