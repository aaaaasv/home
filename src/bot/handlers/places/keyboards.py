"""The places list and item buttons."""
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.formatting import shorten_for_button
from src.bot.handlers.places.messages import PLACES_VISIT_BUTTON
from src.bot.messages import BACK_BUTTON, REMOVE_BUTTON, RENAME_BUTTON
from src.modules.places.domain import PlaceDetails, PlacesList


def build_places_list_keyboard(places: PlacesList) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for place in places.to_visit:
        builder.button(
            text=shorten_for_button(place.name),
            callback_data=PlaceCallback(action=PlaceAction.OPEN, place_id=place.id),
        )
    builder.adjust(2)
    return builder.as_markup()


def build_place_item_keyboard(place: PlaceDetails) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=PLACES_VISIT_BUTTON, callback_data=PlaceCallback(action=PlaceAction.VISIT, place_id=place.id))
    builder.button(text=RENAME_BUTTON, callback_data=PlaceCallback(action=PlaceAction.RENAME, place_id=place.id))
    builder.button(text=REMOVE_BUTTON, callback_data=PlaceCallback(action=PlaceAction.REMOVE, place_id=place.id))
    builder.button(text=BACK_BUTTON, callback_data=PlaceCallback(action=PlaceAction.DISMISS).pack())
    builder.adjust(2)
    return builder.as_markup()


class PlaceAction(StrEnum):
    OPEN = "open"
    VISIT = "visit"
    REMOVE = "remove"
    RENAME = "rename"
    DISMISS = "dismiss"


class PlaceCallback(CallbackData, prefix="place"):
    action: PlaceAction
    place_id: int = 0
