"""The air conditioner card buttons."""
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.handlers.air_conditioner.messages import (
    AIR_CONDITIONER_ACTIVE_MODE_MARKER,
    AIR_CONDITIONER_BUTTON_COOLER,
    AIR_CONDITIONER_BUTTON_FAN,
    AIR_CONDITIONER_BUTTON_QUIET,
    AIR_CONDITIONER_BUTTON_QUIET_ICON,
    AIR_CONDITIONER_BUTTON_TURBO,
    AIR_CONDITIONER_BUTTON_TURBO_ICON,
    AIR_CONDITIONER_BUTTON_TURN_OFF,
    AIR_CONDITIONER_BUTTON_TURN_ON,
    AIR_CONDITIONER_BUTTON_WARMER,
    AIR_CONDITIONER_BUTTON_XFAN,
    AIR_CONDITIONER_BUTTON_XFAN_ICON,
    AIR_CONDITIONER_FAN_SPEED_LABELS,
    AIR_CONDITIONER_MODE_ICONS,
    AIR_CONDITIONER_MODE_LABELS,
)
from src.modules.air_conditioner.domain import AirConditionerFanSpeed, AirConditionerMode, AirConditionerState

# heat is deliberately absent: this is a cooling-season control, and a mistap into heat in july is expensive
AIR_CONDITIONER_OFFERED_MODES = (
    AirConditionerMode.COOL,
    AirConditionerMode.DRY,
    AirConditionerMode.FAN,
)

# one button steps through these in order, wrapping — four legible stops instead of the unit's six
AIR_CONDITIONER_FAN_SPEED_CYCLE = (
    AirConditionerFanSpeed.AUTO,
    AirConditionerFanSpeed.LOW,
    AirConditionerFanSpeed.MEDIUM,
    AirConditionerFanSpeed.HIGH,
)


def next_fan_speed(current: AirConditionerFanSpeed) -> AirConditionerFanSpeed:
    index = AIR_CONDITIONER_FAN_SPEED_CYCLE.index(current)
    return AIR_CONDITIONER_FAN_SPEED_CYCLE[(index + 1) % len(AIR_CONDITIONER_FAN_SPEED_CYCLE)]


class AirConditionerAction(StrEnum):
    SET_POWER = "power"
    WARMER = "warmer"
    COOLER = "cooler"
    SET_MODE = "mode"
    REFRESH = "refresh"
    SET_FAN = "fan"
    TOGGLE_TURBO = "turbo"
    TOGGLE_QUIET = "quiet"
    TOGGLE_XFAN = "xfan"
    # turn off from a transient alert card, then delete the card — it exists only to offer this one action
    STOP_AND_DISMISS = "stop_dismiss"


class AirConditionerCallback(CallbackData, prefix="ac"):
    action: AirConditionerAction
    mode: AirConditionerMode | None = None
    # the end state the button promises, decided when it is drawn — a bare "toggle" would undo a press that
    # someone else already made, turning the unit back on when both of them wanted it off. shared by the power
    # button and every on/off toggle (turbo, quiet, xfan), since a callback only ever carries one action
    turn_on: bool | None = None
    # the fan speed the SET_FAN button steps to, chosen when the card is drawn for the same anti-race reason
    fan_speed: AirConditionerFanSpeed | None = None


def build_air_conditioner_keyboard(state: AirConditionerState) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=AIR_CONDITIONER_BUTTON_TURN_OFF if state.is_on else AIR_CONDITIONER_BUTTON_TURN_ON,
        callback_data=AirConditionerCallback(action=AirConditionerAction.SET_POWER, turn_on=not state.is_on),
    )
    builder.button(
        text=AIR_CONDITIONER_BUTTON_COOLER,
        callback_data=AirConditionerCallback(action=AirConditionerAction.COOLER),
    )
    builder.button(
        text=f"{state.target_temperature_celsius}°",
        callback_data=AirConditionerCallback(action=AirConditionerAction.REFRESH),
    )
    builder.button(
        text=AIR_CONDITIONER_BUTTON_WARMER,
        callback_data=AirConditionerCallback(action=AirConditionerAction.WARMER),
    )
    for mode in AIR_CONDITIONER_OFFERED_MODES:
        prefix = AIR_CONDITIONER_ACTIVE_MODE_MARKER if mode == state.mode else AIR_CONDITIONER_MODE_ICONS[mode]
        builder.button(
            text=f"{prefix} {AIR_CONDITIONER_MODE_LABELS[mode]}",
            callback_data=AirConditionerCallback(action=AirConditionerAction.SET_MODE, mode=mode),
        )

    rows = [1, 3, len(AIR_CONDITIONER_OFFERED_MODES)]
    if state.is_on:
        # airflow controls only matter while it runs, so an off unit keeps the tidy power/temp/mode card
        _add_air_conditioner_airflow_buttons(builder, state)
        rows += [1, 3]

    builder.adjust(*rows)
    return builder.as_markup()


def _add_air_conditioner_airflow_buttons(builder: InlineKeyboardBuilder, state: AirConditionerState) -> None:
    builder.button(
        text=AIR_CONDITIONER_BUTTON_FAN.format(speed=AIR_CONDITIONER_FAN_SPEED_LABELS[state.fan_speed]),
        callback_data=AirConditionerCallback(
            action=AirConditionerAction.SET_FAN, fan_speed=next_fan_speed(state.fan_speed)
        ),
    )
    for is_on, action, label, icon in (
        (
            state.turbo,
            AirConditionerAction.TOGGLE_TURBO,
            AIR_CONDITIONER_BUTTON_TURBO,
            AIR_CONDITIONER_BUTTON_TURBO_ICON,
        ),
        (
            state.quiet,
            AirConditionerAction.TOGGLE_QUIET,
            AIR_CONDITIONER_BUTTON_QUIET,
            AIR_CONDITIONER_BUTTON_QUIET_ICON,
        ),
        (state.xfan, AirConditionerAction.TOGGLE_XFAN, AIR_CONDITIONER_BUTTON_XFAN, AIR_CONDITIONER_BUTTON_XFAN_ICON),
    ):
        prefix = AIR_CONDITIONER_ACTIVE_MODE_MARKER if is_on else icon
        builder.button(
            text=f"{prefix} {label}",
            callback_data=AirConditionerCallback(action=action, turn_on=not is_on),
        )


def build_air_conditioner_stop_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=AIR_CONDITIONER_BUTTON_TURN_OFF,
        callback_data=AirConditionerCallback(action=AirConditionerAction.STOP_AND_DISMISS, turn_on=False),
    )
    return builder.as_markup()
