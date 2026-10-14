"""The strip's buttons: one to put it out, and a few levels worth a single tap."""
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.handlers.lighting.messages import LIGHT_STRIP_BUTTON_LEVEL, LIGHT_STRIP_BUTTON_OFF
from src.modules.lighting.domain import PanelLightState

# the first notch for a dark room, the level both automatic users pick, half, and the top of the travel.
# a continuous slider is what apple home is for; this is the pult for when apple home cannot be reached
STRIP_LEVELS = (5, 20, 50, 100)


class StripCallback(CallbackData, prefix="strip"):
    # the level the button brings about, fixed when the card is drawn, so a stale tap cannot toggle anything
    percent: int


def build_strip_keyboard(state: PanelLightState) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if state.is_on:
        # the one button somebody reaches for at four in the morning, and it stands alone above the levels
        builder.button(text=LIGHT_STRIP_BUTTON_OFF, callback_data=StripCallback(percent=0), style="primary")
    for percent in STRIP_LEVELS:
        builder.button(
            text=LIGHT_STRIP_BUTTON_LEVEL.format(percent=percent), callback_data=StripCallback(percent=percent)
        )
    if state.is_on:
        builder.adjust(1, len(STRIP_LEVELS))
    else:
        builder.adjust(len(STRIP_LEVELS))
    return builder.as_markup()
