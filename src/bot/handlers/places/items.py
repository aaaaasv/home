import re
from collections.abc import Callable
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.places import messages
from src.bot.handlers.places.board import PlacesBoard
from src.bot.handlers.places.keyboards import PlaceAction, PlaceCallback, build_place_item_keyboard
from src.bot.message_cleanup import (
    confirm_captured,
    delete_quietly,
    remember_transient_message,
    sweep_transient_messages,
)
from src.common.domain import Actor
from src.common.time import current_time
from src.infrastructure.db.uow import UnitOfWork
from src.modules.places.commands import AddPlaceCommand, MarkPlaceVisitedCommand, RemovePlaceCommand, RenamePlaceCommand
from src.modules.places.constants import PLACE_NAME_MAX_LENGTH
from src.modules.places.use_cases.add_place import AddPlaceUseCase
from src.modules.places.use_cases.mark_place_visited import MarkPlaceVisitedUseCase
from src.modules.places.use_cases.remove_place import RemovePlaceUseCase
from src.modules.places.use_cases.rename_place import RenamePlaceUseCase
from src.modules.places.use_cases.retrieve_places import RetrievePlacesUseCase

router = Router(name="places_items")

URL_PATTERN = re.compile(r"https?://\S+")


class PlaceStates(StatesGroup):
    new_name = State()


@router.message(Command("list"))
async def show_list(
    message: Message,
    uow_factory: Callable[[], UnitOfWork],
    places_board: PlacesBoard,
) -> None:
    places = await RetrievePlacesUseCase(uow=uow_factory())()
    await places_board.repost(places)
    await delete_quietly(message)


# registered before the plain-text catch-all: while renaming, text is the new name, not a new place
@router.message(PlaceStates.new_name, F.text)
async def receive_new_name(
    message: Message,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
    places_board: PlacesBoard,
) -> None:
    name = message.text.strip()
    collected_data = await state.get_data()
    if len(name) > PLACE_NAME_MAX_LENGTH:
        await delete_quietly(message)
        await message.answer(messages.PLACES_NAME_TOO_LONG)
        return

    await state.clear()
    places = await RenamePlaceUseCase(uow=uow_factory())(
        RenamePlaceCommand(place_id=collected_data["place_id"], name=name)
    )
    await delete_quietly(message)
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await places_board.refresh(places)


# commands are excluded, or a mistyped /list here would land on the list as a place called "/list"
@router.message(F.text, ~F.text.startswith("/"))
async def add_place(
    message: Message,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    places_board: PlacesBoard,
) -> None:
    """Plain text is the whole point: saving a place must be cheaper than remembering it, so it takes no command."""
    name, link = _split_name_and_link(message.text)
    if not name:
        name = link  # a bare link with no name of its own — better than dropping it silently
    if len(name) > PLACE_NAME_MAX_LENGTH:
        await message.answer(messages.PLACES_NAME_TOO_LONG)
        return

    places = await AddPlaceUseCase(uow=uow_factory(), actor=actor)(AddPlaceCommand(name=name, link=link))
    await confirm_captured(message)
    await places_board.refresh(places)


@router.callback_query(PlaceCallback.filter(F.action == PlaceAction.OPEN))
async def open_place(
    callback: CallbackQuery,
    callback_data: PlaceCallback,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    await callback.answer()
    place = await _find_place(callback_data.place_id, uow_factory)
    if place is None:
        return
    await callback.message.answer(f"<b>{escape(place.name)}</b>", reply_markup=build_place_item_keyboard(place))


@router.callback_query(PlaceCallback.filter(F.action == PlaceAction.VISIT))
async def mark_visited(
    callback: CallbackQuery,
    callback_data: PlaceCallback,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    places_board: PlacesBoard,
) -> None:
    places = await MarkPlaceVisitedUseCase(uow=uow_factory(), actor=actor, visited_at=current_time())(
        MarkPlaceVisitedCommand(place_id=callback_data.place_id)
    )
    await callback.answer(messages.PLACES_VISITED_TOAST)
    await delete_quietly(callback.message)
    await places_board.refresh(places)


@router.callback_query(PlaceCallback.filter(F.action == PlaceAction.REMOVE))
async def remove_place(
    callback: CallbackQuery,
    callback_data: PlaceCallback,
    uow_factory: Callable[[], UnitOfWork],
    places_board: PlacesBoard,
) -> None:
    places = await RemovePlaceUseCase(uow=uow_factory())(RemovePlaceCommand(place_id=callback_data.place_id))
    await callback.answer()
    await delete_quietly(callback.message)
    await places_board.refresh(places)


@router.callback_query(PlaceCallback.filter(F.action == PlaceAction.RENAME))
async def rename_place(
    callback: CallbackQuery,
    callback_data: PlaceCallback,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    await callback.answer()
    place = await _find_place(callback_data.place_id, uow_factory)
    await delete_quietly(callback.message)
    prompt = await callback.message.answer(
        messages.PLACES_ASK_NEW_NAME.format(name=place.name if place else ""), disable_notification=True
    )
    await state.set_state(PlaceStates.new_name)
    await state.update_data(place_id=callback_data.place_id)
    await remember_transient_message(state, prompt)


@router.callback_query(PlaceCallback.filter(F.action == PlaceAction.DISMISS))
async def dismiss_place_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await delete_quietly(callback.message)


async def _find_place(place_id: int, uow_factory: Callable[[], UnitOfWork]):
    places = await RetrievePlacesUseCase(uow=uow_factory())()
    return next((place for place in places.to_visit if place.id == place_id), None)


def _split_name_and_link(text: str) -> tuple[str, str | None]:
    match = URL_PATTERN.search(text)
    if match is None:
        return text.strip(), None
    link = match.group(0)
    name = (text[: match.start()] + text[match.end() :]).strip(" —-\t\n")
    return name, link
