"""The one button an alert card carries: the strip the alert has just raised."""
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.handlers.air_alert.messages import AIR_ALERT_BUTTON_STRIP_OFF


class AlertStripCallback(CallbackData, prefix="alertstrip"):
    """Carries nothing: there is one thing to do to a strip from an alert card, and that is put it out."""


def build_alert_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=AIR_ALERT_BUTTON_STRIP_OFF, callback_data=AlertStripCallback())
    return builder.as_markup()
