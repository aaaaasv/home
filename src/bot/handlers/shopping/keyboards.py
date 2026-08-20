"""The shopping list and item buttons."""
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.formatting import shorten_for_button
from src.bot.handlers.shopping.messages import (
    SHOPPING_BUY_BUTTON,
    SHOPPING_NOTE_ADD_BUTTON,
    SHOPPING_NOTE_EDIT_BUTTON,
    SHOPPING_PHOTO_ADD_BUTTON,
    SHOPPING_PHOTO_REPLACE_BUTTON,
    SHOPPING_PROMOTE_BUTTON,
    SHOPPING_TRACK_BUTTON,
)
from src.bot.messages import BACK_BUTTON, REMOVE_BUTTON, RENAME_BUTTON
from src.modules.shopping.constants import ShoppingHorizon
from src.modules.shopping.domain import ShoppingItemDetails, ShoppingList


class ShoppingAction(StrEnum):
    # tapping an item opens its menu; every other action acts on that one item
    OPEN = "open"
    BUY = "buy"
    PROMOTE = "promote"
    TRACK = "track"
    PHOTO = "photo"
    NOTE = "note"
    REMOVE = "remove"
    RENAME = "rename"
    DISMISS = "dismiss"


class ShoppingCallback(CallbackData, prefix="shop"):
    action: ShoppingAction
    item_id: int = 0


def build_shopping_list_keyboard(shopping_list: ShoppingList) -> InlineKeyboardMarkup:
    # one button per item; tapping it opens that item's menu (buy, rename, remove, …), so nothing is ambiguous
    builder = InlineKeyboardBuilder()
    for item in shopping_list.needed_now + shopping_list.wanted_later:
        marker = f"{'🔖' if item.is_tracked else ''}{'📷' if item.has_photo else ''}"
        builder.button(
            text=f"{marker + ' ' if marker else ''}{shorten_for_button(item.name)}",
            callback_data=ShoppingCallback(action=ShoppingAction.OPEN, item_id=item.id),
        )
    builder.adjust(2)
    return builder.as_markup()


def build_shopping_item_keyboard(item: ShoppingItemDetails) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=SHOPPING_BUY_BUTTON, callback_data=ShoppingCallback(action=ShoppingAction.BUY, item_id=item.id))
    builder.button(text=RENAME_BUTTON, callback_data=ShoppingCallback(action=ShoppingAction.RENAME, item_id=item.id))
    if item.horizon == ShoppingHorizon.LATER:
        builder.button(
            text=SHOPPING_PROMOTE_BUTTON, callback_data=ShoppingCallback(action=ShoppingAction.PROMOTE, item_id=item.id)
        )
    if not item.is_tracked:
        builder.button(
            text=SHOPPING_TRACK_BUTTON, callback_data=ShoppingCallback(action=ShoppingAction.TRACK, item_id=item.id)
        )
    builder.button(
        text=SHOPPING_PHOTO_REPLACE_BUTTON if item.has_photo else SHOPPING_PHOTO_ADD_BUTTON,
        callback_data=ShoppingCallback(action=ShoppingAction.PHOTO, item_id=item.id),
    )
    builder.button(
        text=SHOPPING_NOTE_EDIT_BUTTON if item.has_note else SHOPPING_NOTE_ADD_BUTTON,
        callback_data=ShoppingCallback(action=ShoppingAction.NOTE, item_id=item.id),
    )
    builder.button(text=REMOVE_BUTTON, callback_data=ShoppingCallback(action=ShoppingAction.REMOVE, item_id=item.id))
    builder.button(text=BACK_BUTTON, callback_data=ShoppingCallback(action=ShoppingAction.DISMISS).pack())
    builder.adjust(2)
    return builder.as_markup()
