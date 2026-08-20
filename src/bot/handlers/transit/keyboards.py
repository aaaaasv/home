"""The transit arrival card button."""
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.handlers.transit.messages import TRANSIT_BUTTON_REFRESH


class TransitCallback(CallbackData, prefix="transit"):
    action: str = "refresh"


def build_transit_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=TRANSIT_BUTTON_REFRESH, callback_data=TransitCallback())
    return builder.as_markup()
