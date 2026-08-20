import logging
from collections.abc import Callable
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.air_conditioner.formatting import render_air_conditioner
from src.bot.handlers.air_conditioner.keyboards import (
    AIR_CONDITIONER_OFFERED_MODES,
    AirConditionerAction,
    AirConditionerCallback,
    build_air_conditioner_keyboard,
)
from src.bot.handlers.air_conditioner.messages import (
    AIR_CONDITIONER_ALREADY_OFF,
    AIR_CONDITIONER_CARD_EXPIRED,
    AIR_CONDITIONER_TURNED_OFF,
    AIR_CONDITIONER_UNREACHABLE,
    AIR_CONDITIONER_WORKING,
)
from src.bot.services.posted_message_tracker import AIR_CONDITIONER_CARD_KIND, PostedMessageTracker
from src.common.config import Settings
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_conditioner.domain import AirConditionerState
from src.modules.air_conditioner.services.air_conditioner import AirConditioner
from src.modules.plant_care.services.room_climate_sensor import RoomClimate
from src.modules.plant_care.use_cases.retrieve_room_climate import RetrieveRoomClimateUseCase
from src.modules.weather.domain import VentilationEffect
from src.modules.weather.services.ventilation import resolve_ventilation_effect
from src.modules.weather.services.weather_provider import WeatherProvider

logger = logging.getLogger(__name__)

router = Router(name="air_conditioner_card")


@router.message(Command("ac"))
async def show_air_conditioner(
    message: Message,
    air_conditioner: AirConditioner,
    weather_provider: WeatherProvider,
    settings: Settings,
    posted_message_tracker: PostedMessageTracker,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    state = await air_conditioner.read_state()
    if state is None:
        await message.answer(AIR_CONDITIONER_UNREACHABLE)
        return

    indoor, ventilation = await _read_room(weather_provider, uow_factory, live=True)
    # drop any earlier control panel so only the newest one is live
    await posted_message_tracker.clear(AIR_CONDITIONER_CARD_KIND)
    sent = await message.answer(
        render_air_conditioner(
            state, settings.AIR_CONDITIONER_ROOM, datetime.now(settings.timezone), indoor, ventilation
        ),
        reply_markup=build_air_conditioner_keyboard(state),
    )
    await posted_message_tracker.remember(AIR_CONDITIONER_CARD_KIND, sent)


@router.callback_query(AirConditionerCallback.filter(F.action == AirConditionerAction.STOP_AND_DISMISS))
async def stop_air_conditioner_and_dismiss_alert(
    callback: CallbackQuery,
    air_conditioner: AirConditioner,
) -> None:
    # this button rides only on a transient alert (everyone-left / long-run); once the unit is off the card has
    # nothing left to say, so it turns the unit off and then removes itself rather than morphing into a control panel
    state = await air_conditioner.read_state()
    if state is None:
        await callback.answer(AIR_CONDITIONER_UNREACHABLE, show_alert=True)
        return

    if state.is_on:
        if await air_conditioner.apply(is_on=False) is None:
            await callback.answer(AIR_CONDITIONER_UNREACHABLE, show_alert=True)
            return
        await callback.answer(AIR_CONDITIONER_TURNED_OFF)
    else:
        await callback.answer(AIR_CONDITIONER_ALREADY_OFF)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        # older than 48h or already gone — nothing to remove
        pass


@router.callback_query(AirConditionerCallback.filter())
async def handle_air_conditioner_action(
    callback: CallbackQuery,
    callback_data: AirConditionerCallback,
    air_conditioner: AirConditioner,
    weather_provider: WeatherProvider,
    settings: Settings,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    # ack now: reaching the unit over udp can outlast telegram's callback window, and an answer that arrives late
    # fails with "query is too old" while the button keeps spinning. from here on the card itself is the feedback
    await callback.answer()

    # one command already in flight (a transient slow moment on the unit or wi-fi) — drop this tap rather than queue
    # it behind the lock, so three impatient taps do not stack into three commands the unit beeps out in a row
    if air_conditioner.busy:
        return

    # show the tap registered before the (possibly slow, occasionally flaky) round-trip — a stall must not read as
    # "nothing happened"; the result edit below restores the full card or turns it into the unreachable notice
    await _mark_working(callback)

    if callback_data.action == AirConditionerAction.REFRESH:
        await _show(callback, await air_conditioner.read_state(), weather_provider, settings, uow_factory)
        return

    if callback_data.action in (AirConditionerAction.WARMER, AirConditionerAction.COOLER):
        await _apply_temperature(callback, callback_data, air_conditioner, weather_provider, settings, uow_factory)
        return

    # every other button carries the absolute end state, so it applies without a prior read — one round-trip, not two
    await _show(
        callback, await _apply_action(callback_data, None, air_conditioner), weather_provider, settings, uow_factory
    )


async def _apply_temperature(
    callback: CallbackQuery,
    callback_data: AirConditionerCallback,
    air_conditioner: AirConditioner,
    weather_provider: WeatherProvider,
    settings: Settings,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    # warmer/cooler is the one relative action, so it alone must read the current target before stepping it
    state = await air_conditioner.read_state()
    if state is None:
        await _show(callback, None, weather_provider, settings, uow_factory)
        return

    target = _requested_temperature(callback_data, state)
    if not settings.AIR_CONDITIONER_MIN_TEMPERATURE <= target <= settings.AIR_CONDITIONER_MAX_TEMPERATURE:
        # already at the limit — nothing to send, so just leave the card as it stands
        await _show(callback, state, weather_provider, settings, uow_factory)
        return

    await _show(
        callback,
        await air_conditioner.apply(target_temperature_celsius=target),
        weather_provider,
        settings,
        uow_factory,
    )


async def _mark_working(callback: CallbackQuery) -> None:
    # replace the card with a brief note and drop its buttons, so a slow or flaky command reads as in-progress; the
    # result edit restores the full card. an un-editable card (older than 48h) just falls through
    try:
        await callback.message.edit_text(AIR_CONDITIONER_WORKING)
    except TelegramBadRequest:
        pass


async def _show(
    callback: CallbackQuery,
    state: AirConditionerState | None,
    weather_provider: WeatherProvider,
    settings: Settings,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    if state is None:
        # never leave the working card hanging on "⏳": with no live state there are no controls to draw, so the card
        # itself becomes the unreachable notice — an edit, not a new message, so nothing pings
        try:
            await callback.message.edit_text(AIR_CONDITIONER_UNREACHABLE)
        except TelegramBadRequest:
            pass
        return

    indoor, ventilation = await _read_room(weather_provider, uow_factory)
    try:
        await callback.message.edit_text(
            render_air_conditioner(
                state, settings.AIR_CONDITIONER_ROOM, datetime.now(settings.timezone), indoor, ventilation
            ),
            reply_markup=build_air_conditioner_keyboard(state),
        )
    except TelegramBadRequest as error:
        # a bot may edit its own message for 48 hours only; past that the unit still obeyed, so say so in a fresh
        # message. an unchanged card (an absolute button tapped while already in that state) also lands here — no-op
        if "message is not modified" not in str(error):
            await callback.message.answer(AIR_CONDITIONER_CARD_EXPIRED, disable_notification=True)


async def _read_room(
    weather_provider: WeatherProvider, uow_factory: Callable[[], UnitOfWork], live: bool = False
) -> tuple[RoomClimate | None, VentilationEffect | None]:
    indoor = await RetrieveRoomClimateUseCase(uow=uow_factory())()
    if indoor is None:
        return None, None

    # a button tap must not hang on a live weather call — only opening the /ac card fetches, taps reuse that
    outdoor = await weather_provider.fetch() if live else weather_provider.recent()
    if outdoor is None or outdoor.relative_humidity_percent is None:
        return indoor, None

    return indoor, resolve_ventilation_effect(
        indoor_temperature_celsius=indoor.temperature_celsius,
        indoor_humidity_percent=indoor.relative_humidity_percent,
        outdoor_temperature_celsius=outdoor.temperature_celsius,
        outdoor_humidity_percent=outdoor.relative_humidity_percent,
    )


def _requested_temperature(callback_data: AirConditionerCallback, state: AirConditionerState) -> int:
    step = 1 if callback_data.action == AirConditionerAction.WARMER else -1
    return state.target_temperature_celsius + step


async def _apply_action(
    callback_data: AirConditionerCallback,
    state: AirConditionerState | None,
    air_conditioner: AirConditioner,
) -> AirConditionerState | None:
    if callback_data.action == AirConditionerAction.SET_POWER:
        # obey the end state the button promised, not a toggle of whatever the unit happens to be doing now
        return await air_conditioner.apply(is_on=bool(callback_data.turn_on))

    if callback_data.action == AirConditionerAction.SET_MODE:
        # a mode the keyboard never offers can only arrive from a hand-made payload — heat in july is expensive
        if callback_data.mode not in AIR_CONDITIONER_OFFERED_MODES:
            return None
        return await air_conditioner.apply(mode=callback_data.mode, is_on=True)

    if callback_data.action == AirConditionerAction.SET_FAN:
        # choosing a speed by hand is explicit, so it clears turbo/quiet, which would otherwise override it
        return await air_conditioner.apply(fan_speed=callback_data.fan_speed, turbo=False, quiet=False)

    if callback_data.action == AirConditionerAction.TOGGLE_TURBO:
        turning_on = bool(callback_data.turn_on)
        # turbo and quiet are opposite extremes of airflow — turning one on drops the other
        return await air_conditioner.apply(turbo=turning_on, quiet=False if turning_on else None)

    if callback_data.action == AirConditionerAction.TOGGLE_QUIET:
        turning_on = bool(callback_data.turn_on)
        return await air_conditioner.apply(quiet=turning_on, turbo=False if turning_on else None)

    if callback_data.action == AirConditionerAction.TOGGLE_XFAN:
        return await air_conditioner.apply(xfan=bool(callback_data.turn_on))

    return await air_conditioner.apply(target_temperature_celsius=_requested_temperature(callback_data, state))
