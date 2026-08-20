import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.power.formatting import render_ecoflow
from src.bot.handlers.power.keyboards import EcoFlowAction, EcoFlowCallback, build_ecoflow_keyboard
from src.bot.handlers.power.messages import (
    POWER_ECOFLOW_CARD_EXPIRED,
    POWER_ECOFLOW_READING,
    POWER_ECOFLOW_UNREACHABLE,
    POWER_ECOFLOW_WORKING_TOAST,
)
from src.bot.services.posted_message_tracker import ECOFLOW_CARD_KIND, PostedMessageTracker
from src.modules.power.domain import EcoFlowState
from src.modules.power.services.ecoflow_station import EcoFlowStation

logger = logging.getLogger(__name__)

router = Router(name="ecoflow")


@router.message(Command("eco"))
async def show_ecoflow(
    message: Message,
    ecoflow_station: EcoFlowStation,
    posted_message_tracker: PostedMessageTracker,
) -> None:
    # a warm cache answers instantly; a cold one (right after a restart) waits on a ble scan, so post a placeholder
    # first and edit it into the card — the same message becomes the tracked control panel
    placeholder = await message.answer(POWER_ECOFLOW_READING)
    state = await ecoflow_station.read_state()
    if state is None:
        await placeholder.edit_text(POWER_ECOFLOW_UNREACHABLE)
        return

    # drop any earlier control panel so only the newest one is live
    await posted_message_tracker.clear(ECOFLOW_CARD_KIND)
    await placeholder.edit_text(render_ecoflow(state), reply_markup=build_ecoflow_keyboard(state))
    await posted_message_tracker.remember(ECOFLOW_CARD_KIND, placeholder)


@router.callback_query(EcoFlowCallback.filter(F.action == EcoFlowAction.REFRESH))
async def refresh_ecoflow(callback: CallbackQuery, ecoflow_station: EcoFlowStation) -> None:
    # a live read is a ~15s ble round-trip — acknowledge at once so the button never looks frozen, then edit the card
    await _answer_quietly(callback, POWER_ECOFLOW_WORKING_TOAST)
    state = await ecoflow_station.read_state(refresh=True)
    if state is None:
        await _note(callback, POWER_ECOFLOW_UNREACHABLE)
        return
    await _redraw(callback, state)


@router.callback_query(EcoFlowCallback.filter())
async def handle_ecoflow_action(
    callback: CallbackQuery,
    callback_data: EcoFlowCallback,
    ecoflow_station: EcoFlowStation,
) -> None:
    # obey the end state the button promised, not a toggle of whatever the station happens to be doing now
    await _answer_quietly(callback, POWER_ECOFLOW_WORKING_TOAST)
    updated = await _apply_action(callback_data, ecoflow_station)
    if updated is None:
        await _note(callback, POWER_ECOFLOW_UNREACHABLE)
        return
    await _redraw(callback, updated)


async def _apply_action(callback_data: EcoFlowCallback, ecoflow_station: EcoFlowStation) -> EcoFlowState | None:
    if callback_data.action == EcoFlowAction.TOGGLE_AC:
        return await ecoflow_station.apply(ac_output=bool(callback_data.turn_on))
    if callback_data.action == EcoFlowAction.TOGGLE_USB:
        return await ecoflow_station.apply(usb_output=bool(callback_data.turn_on))
    if callback_data.action == EcoFlowAction.TOGGLE_DC:
        return await ecoflow_station.apply(dc_output=bool(callback_data.turn_on))
    return None


async def _redraw(callback: CallbackQuery, state: EcoFlowState) -> None:
    try:
        await callback.message.edit_text(render_ecoflow(state), reply_markup=build_ecoflow_keyboard(state))
    except TelegramBadRequest as error:
        # a bot may edit its own message for 48 hours only; past that the station still obeyed, so say so
        if "message is not modified" not in str(error):
            await _note(callback, POWER_ECOFLOW_CARD_EXPIRED)


async def _note(callback: CallbackQuery, text: str) -> None:
    # the callback was already answered with the working toast, so a follow-up fact goes as a short message
    try:
        await callback.message.answer(text)
    except TelegramBadRequest:
        pass


async def _answer_quietly(callback: CallbackQuery, text: str | None = None) -> None:
    try:
        await callback.answer(text)
    except TelegramBadRequest:
        # a ble round-trip can outlast the callback token; the edit already showed the user the result
        pass
