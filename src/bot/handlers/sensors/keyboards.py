"""The climate card's refresh button."""
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.handlers.sensors.messages import CLIMATE_BUTTON_REFRESH


class ClimateCardCallback(CallbackData, prefix="climate_card"):
    action: str = "refresh"


def build_climate_card_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=CLIMATE_BUTTON_REFRESH, callback_data=ClimateCardCallback())
    return builder.as_markup()
