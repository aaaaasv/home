import logging
from collections.abc import Callable

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.power.conservation_board import ConservationBoard
from src.bot.handlers.power.formatting import render_conservation_status
from src.bot.handlers.power.keyboards import ConservationCallback, build_conservation_keyboard
from src.bot.handlers.power.messages import POWER_CONSERVATION_IN_USE_TOAST, POWER_CONSERVATION_STORED_TOAST
from src.common.time import current_time
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.services.conservation import ConservationMode, ConservationState, estimate_percent, evaluate
from src.modules.power.services.ecoflow_station import EcoFlowStation
from src.modules.power.use_cases.set_conservation_mode import SetConservationModeUseCase

logger = logging.getLogger(__name__)

router = Router(name="conservation")


@router.message(Command("conserve"))
async def show_conservation(
    message: Message, ecoflow_station: EcoFlowStation, uow_factory: Callable[[], UnitOfWork]
) -> None:
    is_conserved, text = await _status(ecoflow_station, uow_factory)
    await message.answer(text, reply_markup=build_conservation_keyboard(is_conserved))


@router.callback_query(ConservationCallback.filter())
async def toggle_conservation(
    callback: CallbackQuery,
    callback_data: ConservationCallback,
    ecoflow_station: EcoFlowStation,
    uow_factory: Callable[[], UnitOfWork],
    conservation_board: ConservationBoard | None = None,
) -> None:
    conserved = bool(callback_data.turn_on)
    state = await ecoflow_station.read_state()
    await SetConservationModeUseCase(uow=uow_factory(), now=current_time())(
        is_conserved=conserved, battery_percent=state.battery_percent if state is not None else None
    )

    # post or clear the standing storage card right away, then rewrite this control card so the toggle flips
    if conservation_board is not None:
        await conservation_board.refresh()

    is_conserved, text = await _status(ecoflow_station, uow_factory)
    try:
        await callback.message.edit_text(text, reply_markup=build_conservation_keyboard(is_conserved))
    except TelegramBadRequest:
        pass
    await _answer_quietly(callback, POWER_CONSERVATION_STORED_TOAST if conserved else POWER_CONSERVATION_IN_USE_TOAST)


async def _status(ecoflow_station: EcoFlowStation, uow_factory: Callable[[], UnitOfWork]) -> tuple[bool, str]:
    now = current_time()
    async with uow_factory() as uow:
        record = await uow.conservation.get()

    if record is None or not record.is_conserved:
        state = await ecoflow_station.read_state()
        percent = round(state.battery_percent) if state is not None else None
        return False, render_conservation_status(is_conserved=False, percent=percent, advisory=None)

    domain = ConservationState(
        stored_percent=record.stored_percent,
        stored_at=record.stored_at,
        mode=ConservationMode(record.mode),
        last_cycle_at=record.last_cycle_at,
    )
    return True, render_conservation_status(
        is_conserved=True, percent=round(estimate_percent(domain, now)), advisory=evaluate(domain, now)
    )


async def _answer_quietly(callback: CallbackQuery, text: str | None = None) -> None:
    try:
        await callback.answer(text)
    except TelegramBadRequest:
        pass
