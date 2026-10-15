"""The EcoFlow, outage schedule and conservation buttons."""
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.handlers.power.messages import (
    POWER_BOARD_BUTTON_TO_GRID,
    POWER_BOARD_BUTTON_TO_STATION,
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
    POWER_SUPPLY_BUTTON_GRID,
    POWER_SUPPLY_BUTTON_GRID_IS_BACK,
    POWER_SUPPLY_BUTTON_STATION,
)
from src.modules.power.domain import DeclaredSupply, EcoFlowState


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


def build_power_board_keyboard(declared_supply: DeclaredSupply) -> InlineKeyboardMarkup:
    """
    Refresh, and the one control that cannot live on a push: who is feeding the pi's socket.

    it belongs here because the board is the newest message in this topic at any moment — edited every
    minute while the flat is on battery and reposted every morning. the card that announced «світло є»
    carries the same correction, but only until the next message buries it, and «я перемкнувся назад» is
    said ten minutes later, not nineteen seconds later.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=POWER_SCHEDULE_BUTTON_REFRESH, callback_data=OutageScheduleCallback())
    if declared_supply is DeclaredSupply.STATION:
        builder.button(
            text=POWER_BOARD_BUTTON_TO_GRID,
            callback_data=SupplyCallback(supply=DeclaredSupply.GRID, board=True),
            style="primary",
        )
    else:
        builder.button(
            text=POWER_BOARD_BUTTON_TO_STATION,
            callback_data=SupplyCallback(supply=DeclaredSupply.STATION, board=True),
        )
    builder.adjust(2)
    return builder.as_markup()


def build_ecoflow_keyboard(state: EcoFlowState) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=POWER_ECOFLOW_BUTTON_AC_OFF if state.ac_output_on else POWER_ECOFLOW_BUTTON_AC_ON,
        callback_data=EcoFlowCallback(action=EcoFlowAction.TOGGLE_AC, turn_on=not state.ac_output_on),
        # switching the outlets on is what saves the fridge in a blackout, so it must not look like the rest
        style=None if state.ac_output_on else "primary",
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


class SupplyCallback(CallbackData, prefix="supply"):
    """Who is feeding the pi's socket, which journal row the answer takes back (0 for none), and in answer to what."""

    supply: DeclaredSupply
    retract: int = 0
    # set only on «так, мережа»: that card already says the right thing, so it keeps its own text
    confirming: bool = False
    # tapped on the board rather than on a push: the board redraws itself and must not be overwritten
    board: bool = False


def build_supply_keyboard(
    declared_supply: DeclaredSupply, retract_grid_event_id: int = 0, asking: bool = False
) -> InlineKeyboardMarkup:
    """
    The buttons that let a person answer the one question no sensor in the flat can.

    **«світло є» always carries the correction**, whether or not the station is in a state to contradict it:
    that message is the only one that can be wrong, and the station is asleep or out of bluetooth range often
    enough that «only when it contradicts» left the card with nothing to tap. the question above it, and the
    «так, мережа» beside it, appear only when the station does contradict — asking under every restored light
    teaches everybody to ignore the asking.

    the «no» carries the row it retracts, so the same tap on a week-old card cannot cut a hole in the middle
    of the journal. once the station is declared, the only button left is the way back.

    «світло зникло» carries nothing at all any more: it fires before anything has happened, and what has to
    be said ten minutes later — «я перемкнувся назад» — belongs where it can still be found, which is the
    board (`build_power_board_keyboard`).
    """
    builder = InlineKeyboardBuilder()
    if declared_supply is DeclaredSupply.STATION:
        builder.button(
            text=POWER_SUPPLY_BUTTON_GRID_IS_BACK,
            callback_data=SupplyCallback(supply=DeclaredSupply.GRID),
            style="primary",
        )
        return builder.as_markup()

    if asking:
        builder.button(
            text=POWER_SUPPLY_BUTTON_GRID,
            callback_data=SupplyCallback(supply=DeclaredSupply.GRID, confirming=True),
        )
    builder.button(
        text=POWER_SUPPLY_BUTTON_STATION,
        callback_data=SupplyCallback(supply=DeclaredSupply.STATION, retract=retract_grid_event_id),
    )
    builder.adjust(2)
    return builder.as_markup()
