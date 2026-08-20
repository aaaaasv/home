from collections.abc import Callable
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.formatting import exceeds_caption_limit
from src.bot.handlers.shopping import messages
from src.bot.handlers.shopping.board import ShoppingListBoard
from src.bot.handlers.shopping.keyboards import ShoppingAction, ShoppingCallback, build_shopping_item_keyboard
from src.bot.message_cleanup import (
    confirm_captured,
    delete_quietly,
    remember_transient_message,
    sweep_transient_messages,
)
from src.common.domain import Actor
from src.common.exceptions import ValidationError
from src.common.time import current_time
from src.infrastructure.db.uow import UnitOfWork
from src.modules.shopping.commands import (
    AddShoppingItemCommand,
    BuyShoppingItemCommand,
    PromoteShoppingItemCommand,
    RemoveShoppingItemCommand,
    RenameShoppingItemCommand,
    SetShoppingItemNoteCommand,
    SetShoppingItemPhotoCommand,
    TrackExistingItemCommand,
    TrackShoppingItemCommand,
)
from src.modules.shopping.constants import SHOPPING_ITEM_NAME_MAX_LENGTH, SHOPPING_ITEM_NOTE_MAX_LENGTH, ShoppingHorizon
from src.modules.shopping.services.price_source import PriceSource, is_hotline_url
from src.modules.shopping.use_cases.add_shopping_item import AddShoppingItemUseCase
from src.modules.shopping.use_cases.buy_shopping_item import BuyShoppingItemUseCase
from src.modules.shopping.use_cases.promote_shopping_item import PromoteShoppingItemUseCase
from src.modules.shopping.use_cases.remove_shopping_item import RemoveShoppingItemUseCase
from src.modules.shopping.use_cases.rename_shopping_item import RenameShoppingItemUseCase
from src.modules.shopping.use_cases.retrieve_shopping_list import RetrieveShoppingListUseCase
from src.modules.shopping.use_cases.set_shopping_item_note import SetShoppingItemNoteUseCase
from src.modules.shopping.use_cases.set_shopping_item_photo import SetShoppingItemPhotoUseCase
from src.modules.shopping.use_cases.track_existing_item import TrackExistingItemUseCase
from src.modules.shopping.use_cases.track_shopping_item import TrackShoppingItemUseCase

router = Router(name="shopping_items")


class ShoppingItemStates(StatesGroup):
    link = State()
    new_name = State()
    note = State()
    photo = State()


@router.message(Command("list"))
async def show_list(
    message: Message,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
) -> None:
    shopping_list = await RetrieveShoppingListUseCase(uow=uow_factory())()
    await shopping_list_board.repost(shopping_list)
    await delete_quietly(message)


@router.message(Command("add"))
async def add_needed_now_by_command(
    message: Message,
    command: CommandObject,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
) -> None:
    if not command.args:
        await message.answer(messages.SHOPPING_ADD_NEEDS_TEXT)
        return

    await _add_item(command.args, ShoppingHorizon.NOW, message, actor, uow_factory, shopping_list_board)


@router.message(Command("track"))
async def track_item(
    message: Message,
    command: CommandObject,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
    price_source: PriceSource,
) -> None:
    args = command.args
    # the command itself is transient noise once read, so drop it and let the board be the only trace
    await delete_quietly(message)
    if not args:
        await message.answer(messages.TRACK_NEEDS_LINK)
        return

    url = args.strip()
    if not is_hotline_url(url):
        await message.answer(messages.TRACK_NOT_HOTLINE)
        return

    # the fetch hits hotline (~1-2s) with the command already deleted, so leave a status banner in its place
    checking = await message.answer(messages.TRACK_CHECKING)
    try:
        shopping_list = await TrackShoppingItemUseCase(
            uow=uow_factory(), actor=actor, price_source=price_source, checked_at=current_time()
        )(TrackShoppingItemCommand(hotline_url=url))
    except ValidationError:
        # the link is a hotline one but the page did not yield a price — a dead product, or a changed layout
        await checking.edit_text(messages.TRACK_UNREADABLE)
        return

    await delete_quietly(checking)
    await shopping_list_board.refresh(shopping_list)


@router.message(Command("later"))
async def add_wanted_later(
    message: Message,
    command: CommandObject,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
) -> None:
    if not command.args:
        await message.answer(messages.SHOPPING_LATER_NEEDS_TEXT)
        return

    await _add_item(command.args, ShoppingHorizon.LATER, message, actor, uow_factory, shopping_list_board)


# registered before the plain-text catch-all: while waiting for a tracking link, text is the link, not a new item
@router.message(ShoppingItemStates.link, F.text)
async def receive_tracking_link(
    message: Message,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
    price_source: PriceSource,
) -> None:
    url = message.text.strip()
    collected_data = await state.get_data()
    # keep the state on error so the person can just resend a correct link, and drop their bad message
    if not is_hotline_url(url):
        await delete_quietly(message)
        await message.answer(messages.TRACK_NOT_HOTLINE)
        return

    # drop the pasted link and leave a status banner while the hotline fetch (~1-2s) runs
    await delete_quietly(message)
    checking = await message.answer(messages.TRACK_CHECKING)
    try:
        await TrackExistingItemUseCase(uow=uow_factory(), price_source=price_source, checked_at=current_time())(
            TrackExistingItemCommand(item_id=collected_data["item_id"], hotline_url=url)
        )
    except ValidationError:
        await checking.edit_text(messages.TRACK_UNREADABLE)
        return

    await state.clear()
    # the board now shows the price, so the prompt, the pasted link and the banner are just clutter — clear them
    await delete_quietly(checking)
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await shopping_list_board.refresh(await RetrieveShoppingListUseCase(uow=uow_factory())())


@router.message(ShoppingItemStates.new_name, F.text)
async def receive_new_name(
    message: Message,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
) -> None:
    name = message.text.strip()
    collected_data = await state.get_data()
    if len(name) > SHOPPING_ITEM_NAME_MAX_LENGTH:
        await delete_quietly(message)
        await message.answer(messages.SHOPPING_NAME_TOO_LONG)
        return

    await state.clear()
    shopping_list = await RenameShoppingItemUseCase(uow=uow_factory())(
        RenameShoppingItemCommand(item_id=collected_data["item_id"], name=name)
    )
    await delete_quietly(message)
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await shopping_list_board.refresh(shopping_list)


# while attaching a photo to a chosen item, the incoming photo belongs to that item — not a new one
@router.message(ShoppingItemStates.photo, F.photo)
async def receive_item_photo(
    message: Message,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
) -> None:
    collected_data = await state.get_data()
    await state.clear()
    shopping_list = await SetShoppingItemPhotoUseCase(uow=uow_factory())(
        SetShoppingItemPhotoCommand(item_id=collected_data["item_id"], photo_telegram_file_id=message.photo[-1].file_id)
    )
    await delete_quietly(message)
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await shopping_list_board.refresh(shopping_list)


@router.message(ShoppingItemStates.photo)
async def reject_non_photo(message: Message) -> None:
    await delete_quietly(message)
    await message.answer(messages.SHOPPING_PHOTO_EXPECTS_PHOTO)


# commands are excluded, or a mistyped /today here would land on the list as an item called "/today"
@router.message(F.text, ~F.text.startswith("/"))
async def add_needed_now(
    message: Message,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
) -> None:
    """Plain text is the whole point: adding must be cheaper than remembering, so it takes no command at all."""
    await _add_item(message.text, ShoppingHorizon.NOW, message, actor, uow_factory, shopping_list_board)


@router.message(F.photo)
async def add_by_photo(
    message: Message,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
) -> None:
    """A photo with a caption is a hands-free add: the caption names the item and the photo rides along."""
    caption = (message.caption or "").strip()
    if not caption:
        # the board is text, so an item still needs a name — ask for a caption rather than invent one
        await message.answer(messages.SHOPPING_PHOTO_NEEDS_CAPTION)
        return

    await _add_item(
        caption,
        ShoppingHorizon.NOW,
        message,
        actor,
        uow_factory,
        shopping_list_board,
        photo_telegram_file_id=message.photo[-1].file_id,
    )


@router.callback_query(ShoppingCallback.filter(F.action == ShoppingAction.OPEN))
async def open_item(
    callback: CallbackQuery,
    callback_data: ShoppingCallback,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    await callback.answer()
    item = await _find_item(callback_data.item_id, uow_factory)
    if item is None:
        return
    title = f"<b>{escape(item.name)}</b>"
    if item.has_note:
        title += f"\n\n{escape(item.note)}"
    keyboard = build_shopping_item_keyboard(item)
    if item.has_photo and not exceeds_caption_limit(title):
        await callback.message.answer_photo(item.photo_telegram_file_id, caption=title, reply_markup=keyboard)
        return
    if item.has_photo:
        await callback.message.answer_photo(item.photo_telegram_file_id)
    await callback.message.answer(title, reply_markup=keyboard)


@router.callback_query(ShoppingCallback.filter(F.action == ShoppingAction.NOTE))
async def edit_item_note(
    callback: CallbackQuery,
    callback_data: ShoppingCallback,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    await callback.answer()
    item = await _find_item(callback_data.item_id, uow_factory)
    await delete_quietly(callback.message)
    prompt = await callback.message.answer(
        messages.SHOPPING_ASK_NOTE.format(name=item.name if item else ""), disable_notification=True
    )
    await state.set_state(ShoppingItemStates.note)
    await state.update_data(item_id=callback_data.item_id)
    await remember_transient_message(state, prompt)


@router.message(ShoppingItemStates.note, F.text)
async def receive_note(
    message: Message,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
) -> None:
    note = message.text.strip()
    collected_data = await state.get_data()
    if len(note) > SHOPPING_ITEM_NOTE_MAX_LENGTH:
        await delete_quietly(message)
        await message.answer(messages.SHOPPING_NOTE_TOO_LONG)
        return

    await state.clear()
    # a lone dash is how the card goes back to just a name
    shopping_list = await SetShoppingItemNoteUseCase(uow=uow_factory())(
        SetShoppingItemNoteCommand(item_id=collected_data["item_id"], note="" if note == "-" else note)
    )
    await delete_quietly(message)
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await shopping_list_board.refresh(shopping_list)


@router.callback_query(ShoppingCallback.filter(F.action == ShoppingAction.BUY))
async def buy_item(
    callback: CallbackQuery,
    callback_data: ShoppingCallback,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
) -> None:
    shopping_list = await BuyShoppingItemUseCase(uow=uow_factory(), actor=actor)(
        BuyShoppingItemCommand(item_id=callback_data.item_id)
    )
    await callback.answer(messages.SHOPPING_BOUGHT_TOAST)
    await delete_quietly(callback.message)
    await shopping_list_board.refresh(shopping_list)


@router.callback_query(ShoppingCallback.filter(F.action == ShoppingAction.PROMOTE))
async def promote_item(
    callback: CallbackQuery,
    callback_data: ShoppingCallback,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
) -> None:
    shopping_list = await PromoteShoppingItemUseCase(uow=uow_factory())(
        PromoteShoppingItemCommand(item_id=callback_data.item_id)
    )
    await callback.answer()
    await delete_quietly(callback.message)
    await shopping_list_board.refresh(shopping_list)


@router.callback_query(ShoppingCallback.filter(F.action == ShoppingAction.REMOVE))
async def remove_item(
    callback: CallbackQuery,
    callback_data: ShoppingCallback,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
) -> None:
    shopping_list = await RemoveShoppingItemUseCase(uow=uow_factory())(
        RemoveShoppingItemCommand(item_id=callback_data.item_id)
    )
    await callback.answer()
    await delete_quietly(callback.message)
    await shopping_list_board.refresh(shopping_list)


@router.callback_query(ShoppingCallback.filter(F.action == ShoppingAction.TRACK))
async def track_item_from_menu(
    callback: CallbackQuery,
    callback_data: ShoppingCallback,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    await callback.answer()
    item = await _find_item(callback_data.item_id, uow_factory)
    await delete_quietly(callback.message)
    prompt = await callback.message.answer(
        messages.SHOPPING_TRACK_ASK_LINK.format(name=item.name if item else ""), disable_notification=True
    )
    await state.set_state(ShoppingItemStates.link)
    await state.update_data(item_id=callback_data.item_id)
    await remember_transient_message(state, prompt)


@router.callback_query(ShoppingCallback.filter(F.action == ShoppingAction.PHOTO))
async def attach_item_photo(
    callback: CallbackQuery,
    callback_data: ShoppingCallback,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    await callback.answer()
    item = await _find_item(callback_data.item_id, uow_factory)
    await delete_quietly(callback.message)
    prompt = await callback.message.answer(
        messages.SHOPPING_PHOTO_ASK.format(name=item.name if item else ""), disable_notification=True
    )
    await state.set_state(ShoppingItemStates.photo)
    await state.update_data(item_id=callback_data.item_id)
    await remember_transient_message(state, prompt)


@router.callback_query(ShoppingCallback.filter(F.action == ShoppingAction.RENAME))
async def rename_item(
    callback: CallbackQuery,
    callback_data: ShoppingCallback,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    await callback.answer()
    item = await _find_item(callback_data.item_id, uow_factory)
    await delete_quietly(callback.message)
    prompt = await callback.message.answer(
        messages.SHOPPING_ASK_NEW_NAME.format(name=item.name if item else ""), disable_notification=True
    )
    await state.set_state(ShoppingItemStates.new_name)
    await state.update_data(item_id=callback_data.item_id)
    await remember_transient_message(state, prompt)


@router.callback_query(ShoppingCallback.filter(F.action == ShoppingAction.DISMISS))
async def dismiss_item_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await delete_quietly(callback.message)


async def _find_item(item_id: int, uow_factory: Callable[[], UnitOfWork]):
    shopping_list = await RetrieveShoppingListUseCase(uow=uow_factory())()
    return next((item for item in shopping_list.needed_now + shopping_list.wanted_later if item.id == item_id), None)


async def _add_item(
    text: str,
    horizon: ShoppingHorizon,
    message: Message,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    shopping_list_board: ShoppingListBoard,
    photo_telegram_file_id: str | None = None,
) -> None:
    name = text.strip()
    if len(name) > SHOPPING_ITEM_NAME_MAX_LENGTH:
        await message.answer(messages.SHOPPING_NAME_TOO_LONG)
        return

    shopping_list = await AddShoppingItemUseCase(uow=uow_factory(), actor=actor)(
        AddShoppingItemCommand(name=name, horizon=horizon, photo_telegram_file_id=photo_telegram_file_id)
    )
    await confirm_captured(message)
    await shopping_list_board.refresh(shopping_list)
