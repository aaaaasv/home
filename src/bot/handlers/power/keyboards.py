"""The EcoFlow, outage schedule and conservation buttons."""
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.handlers.power.messages import (
    POWER_CONSERVATION_BUTTON_IN_USE,
    POWER_CONSERVATION_BUTTON_STORE,
    POWER_ECOFLOW_BUTTON_AC_OFF,
    POWER_ECOFLOW_BUTTON_AC_ON,
    POWER_ECOFLOW_BUTTON_DC_OFF,
    POWER_ECOFLOW_BUTTON_DC_ON,
    POWER_ECOFLOW_BUTTON_REFRESH,
    POWER_ECOFLOW_BUTTON_USB_OFF,
    POWER_ECOFLOW_BUTTON_USB_ON,
    POWER_SCHEDULE_BUTTON_REFRESH,
)
from src.modules.power.domain import EcoFlowState


class EcoFlowAction(StrEnum):
    TOGGLE_AC = "ac"
    TOGGLE_USB = "usb"
    TOGGLE_DC = "dc"
    REFRESH = "refresh"


class EcoFlowCallback(CallbackData, prefix="eco"):
    action: EcoFlowAction
    # the end state the toggle promises, fixed when the card is drawn — the same anti-race guard the ac card uses
    turn_on: bool | None = None


class ConservationCallback(CallbackData, prefix="cons"):
    # the storage state the /conserve button puts the station into
    turn_on: bool


class OutageScheduleCallback(CallbackData, prefix="outage"):
    action: str = "refresh"


def build_outage_schedule_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=POWER_SCHEDULE_BUTTON_REFRESH, callback_data=OutageScheduleCallback())
    return builder.as_markup()


def build_ecoflow_keyboard(state: EcoFlowState) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=POWER_ECOFLOW_BUTTON_AC_OFF if state.ac_output_on else POWER_ECOFLOW_BUTTON_AC_ON,
        callback_data=EcoFlowCallback(action=EcoFlowAction.TOGGLE_AC, turn_on=not state.ac_output_on),
    )
    builder.button(
        text=POWER_ECOFLOW_BUTTON_USB_OFF if state.usb_output_on else POWER_ECOFLOW_BUTTON_USB_ON,
        callback_data=EcoFlowCallback(action=EcoFlowAction.TOGGLE_USB, turn_on=not state.usb_output_on),
    )
    builder.button(
        text=POWER_ECOFLOW_BUTTON_DC_OFF if state.dc_output_on else POWER_ECOFLOW_BUTTON_DC_ON,
        callback_data=EcoFlowCallback(action=EcoFlowAction.TOGGLE_DC, turn_on=not state.dc_output_on),
    )
    builder.button(text=POWER_ECOFLOW_BUTTON_REFRESH, callback_data=EcoFlowCallback(action=EcoFlowAction.REFRESH))
    # the ac outlet is the outage lifeline, so it stands on its own row above the two dc-side toggles and refresh
    builder.adjust(1, 2, 1)
    return builder.as_markup()


def build_conservation_keyboard(is_conserved: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=POWER_CONSERVATION_BUTTON_IN_USE if is_conserved else POWER_CONSERVATION_BUTTON_STORE,
        callback_data=ConservationCallback(turn_on=not is_conserved),
    )
    return builder.as_markup()
