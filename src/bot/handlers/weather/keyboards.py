"""The weather digest refresh button."""
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.handlers.weather.messages import WEATHER_DIGEST_BUTTON_REFRESH


class WeatherDigestCallback(CallbackData, prefix="weather"):
    action: str = "refresh"


def build_weather_digest_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=WEATHER_DIGEST_BUTTON_REFRESH, callback_data=WeatherDigestCallback())
    return builder.as_markup()
