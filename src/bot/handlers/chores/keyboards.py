"""The chores board and item buttons."""
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.formatting import shorten_for_button
from src.bot.handlers.chores.messages import (
    CHORES_ASSIGN_BUTTON,
    CHORES_ASSIGN_NOBODY,
    CHORES_DEADLINE_BUTTON,
    CHORES_DONE_BUTTON,
)
from src.bot.messages import BACK_BUTTON, REMOVE_BUTTON, RENAME_BUTTON
from src.modules.chores.domain import ChoreDetails, ChoresList
from src.modules.family.domain import FamilyMember


class ChoreAction(StrEnum):
    OPEN = "open"
    DONE = "done"
    DEADLINE = "deadline"
    ASSIGN_MENU = "assign_menu"
    ASSIGN = "assign"
    RENAME = "rename"
    REMOVE = "remove"
    DISMISS = "dismiss"


class ChoreCallback(CallbackData, prefix="chore"):
    action: ChoreAction
    chore_id: int = 0
    # the person picked in the assignee menu; 0 means «нікого» (clear the tag)
    assignee_id: int = 0


def build_chores_list_keyboard(chores: ChoresList) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for chore in chores.open_chores:
        builder.button(
            text=shorten_for_button(chore.name),
            callback_data=ChoreCallback(action=ChoreAction.OPEN, chore_id=chore.id),
        )
    builder.adjust(2)
    return builder.as_markup()


def build_chore_item_keyboard(chore: ChoreDetails) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=CHORES_DONE_BUTTON, callback_data=ChoreCallback(action=ChoreAction.DONE, chore_id=chore.id))
    builder.button(
        text=CHORES_DEADLINE_BUTTON, callback_data=ChoreCallback(action=ChoreAction.DEADLINE, chore_id=chore.id)
    )
    builder.button(
        text=CHORES_ASSIGN_BUTTON, callback_data=ChoreCallback(action=ChoreAction.ASSIGN_MENU, chore_id=chore.id)
    )
    builder.button(text=RENAME_BUTTON, callback_data=ChoreCallback(action=ChoreAction.RENAME, chore_id=chore.id))
    builder.button(text=REMOVE_BUTTON, callback_data=ChoreCallback(action=ChoreAction.REMOVE, chore_id=chore.id))
    builder.button(text=BACK_BUTTON, callback_data=ChoreCallback(action=ChoreAction.DISMISS).pack())
    builder.adjust(2)
    return builder.as_markup()


def build_chore_assignee_keyboard(chore_id: int, members: list[FamilyMember]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for member in members:
        builder.button(
            text=member.first_name,
            callback_data=ChoreCallback(
                action=ChoreAction.ASSIGN, chore_id=chore_id, assignee_id=member.telegram_user_id
            ),
        )
    builder.button(text=CHORES_ASSIGN_NOBODY, callback_data=ChoreCallback(action=ChoreAction.ASSIGN, chore_id=chore_id))
    builder.button(text=BACK_BUTTON, callback_data=ChoreCallback(action=ChoreAction.DISMISS).pack())
    builder.adjust(2)
    return builder.as_markup()
