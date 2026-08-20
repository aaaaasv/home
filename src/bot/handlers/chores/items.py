from collections.abc import Callable
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.chores import messages
from src.bot.handlers.chores.board import ChoresBoard
from src.bot.handlers.chores.keyboards import (
    ChoreAction,
    ChoreCallback,
    build_chore_assignee_keyboard,
    build_chore_item_keyboard,
)
from src.bot.message_cleanup import (
    confirm_captured,
    delete_quietly,
    remember_transient_message,
    sweep_transient_messages,
)
from src.bot.services.posted_message_tracker import CHORE_DEADLINE_KIND, PostedMessageTracker
from src.common.domain import Actor
from src.common.household_calendar import HouseholdCalendar
from src.common.time import current_time
from src.infrastructure.db.uow import UnitOfWork
from src.modules.chores.commands import (
    AddChoreCommand,
    CompleteChoreCommand,
    RemoveChoreCommand,
    RenameChoreCommand,
    SetChoreAssigneeCommand,
    SetChoreDeadlineCommand,
)
from src.modules.chores.constants import CHORE_NAME_MAX_LENGTH
from src.modules.chores.services.deadline_parser import parse_chore_text, parse_deadline, split_assignee
from src.modules.chores.use_cases.add_chore import AddChoreUseCase
from src.modules.chores.use_cases.complete_chore import CompleteChoreUseCase
from src.modules.chores.use_cases.remove_chore import RemoveChoreUseCase
from src.modules.chores.use_cases.rename_chore import RenameChoreUseCase
from src.modules.chores.use_cases.retrieve_chores import RetrieveChoresUseCase
from src.modules.chores.use_cases.set_chore_assignee import SetChoreAssigneeUseCase
from src.modules.chores.use_cases.set_chore_deadline import SetChoreDeadlineUseCase
from src.modules.family.use_cases.list_family_members import ListFamilyMembersUseCase

router = Router(name="chores_items")

CLEAR_DEADLINE_COMMAND = "/clear"


class ChoreStates(StatesGroup):
    new_name = State()
    new_deadline = State()


@router.message(Command("list"))
async def show_list(
    message: Message,
    uow_factory: Callable[[], UnitOfWork],
    chores_board: ChoresBoard,
) -> None:
    chores = await RetrieveChoresUseCase(uow=uow_factory())()
    await chores_board.repost(chores)
    await delete_quietly(message)


# registered before the plain-text catch-all: while renaming, text is the new name, not a new chore
@router.message(ChoreStates.new_name, F.text)
async def receive_new_name(
    message: Message,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
    chores_board: ChoresBoard,
) -> None:
    name = message.text.strip()
    collected_data = await state.get_data()
    if len(name) > CHORE_NAME_MAX_LENGTH:
        await delete_quietly(message)
        await message.answer(messages.CHORES_NAME_TOO_LONG)
        return

    await state.clear()
    chores = await RenameChoreUseCase(uow=uow_factory())(
        RenameChoreCommand(chore_id=collected_data["chore_id"], name=name)
    )
    await delete_quietly(message)
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await chores_board.refresh(chores)


# while setting a deadline, text is the date (or /clear), not a new chore
@router.message(ChoreStates.new_deadline, F.text)
async def receive_deadline(
    message: Message,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    chores_board: ChoresBoard,
    posted_message_tracker: PostedMessageTracker,
) -> None:
    collected_data = await state.get_data()
    chore_id = collected_data["chore_id"]
    text = message.text.strip()

    if text == CLEAR_DEADLINE_COMMAND:
        due_on = None
    else:
        due_on = parse_deadline(text, household_calendar.today())
        if due_on is None:
            # stay in the state so the next line is another try, rather than making them tap the button again
            await delete_quietly(message)
            await message.answer(messages.CHORES_DEADLINE_UNCLEAR, disable_notification=True)
            return

    await state.clear()
    chores = await SetChoreDeadlineUseCase(uow=uow_factory())(SetChoreDeadlineCommand(chore_id=chore_id, due_on=due_on))
    if due_on is None:
        # a chore with no date must not keep a deadline card — drop it now rather than wait for the next sweep
        await posted_message_tracker.clear_one(CHORE_DEADLINE_KIND, str(chore_id))
    await delete_quietly(message)
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await chores_board.refresh(chores)


# commands are excluded, or a mistyped /list here would land on the list as a chore called "/list"
@router.message(F.text, ~F.text.startswith("/"))
async def add_chore(
    message: Message,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    chores_board: ChoresBoard,
) -> None:
    """Plain text is the whole point: saving a chore must be cheaper than remembering it, so it takes no command."""
    members = await ListFamilyMembersUseCase(uow=uow_factory())()
    # a leading known name tags the person, a trailing phrase sets the deadline — «Марта забрати посилку до 31.07»
    assignee, remainder = split_assignee(message.text, members)
    name, due_on = parse_chore_text(remainder, household_calendar.today())
    if not name:
        # the whole line was a name/date phrase and nothing else — keep it verbatim rather than drop it
        name, due_on, assignee = message.text.strip(), None, None
    if len(name) > CHORE_NAME_MAX_LENGTH:
        await message.answer(messages.CHORES_NAME_TOO_LONG)
        return

    chores = await AddChoreUseCase(uow=uow_factory(), actor=actor)(
        AddChoreCommand(
            name=name,
            due_on=due_on,
            assignee_telegram_user_id=assignee.telegram_user_id if assignee else None,
            assignee_display_name=assignee.first_name if assignee else None,
        )
    )
    await confirm_captured(message)
    await chores_board.refresh(chores)


@router.callback_query(ChoreCallback.filter(F.action == ChoreAction.OPEN))
async def open_chore(
    callback: CallbackQuery,
    callback_data: ChoreCallback,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    await callback.answer()
    chore = await _find_chore(callback_data.chore_id, uow_factory)
    if chore is None:
        return
    await callback.message.answer(f"<b>{escape(chore.name)}</b>", reply_markup=build_chore_item_keyboard(chore))


@router.callback_query(ChoreCallback.filter(F.action == ChoreAction.DONE))
async def complete_chore(
    callback: CallbackQuery,
    callback_data: ChoreCallback,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    chores_board: ChoresBoard,
    posted_message_tracker: PostedMessageTracker,
) -> None:
    chores = await CompleteChoreUseCase(uow=uow_factory(), actor=actor, completed_at=current_time())(
        CompleteChoreCommand(chore_id=callback_data.chore_id)
    )
    await callback.answer(messages.CHORES_DONE_TOAST)
    await posted_message_tracker.clear_one(CHORE_DEADLINE_KIND, str(callback_data.chore_id))
    await delete_quietly(callback.message)
    await chores_board.refresh(chores)


@router.callback_query(ChoreCallback.filter(F.action == ChoreAction.REMOVE))
async def remove_chore(
    callback: CallbackQuery,
    callback_data: ChoreCallback,
    uow_factory: Callable[[], UnitOfWork],
    chores_board: ChoresBoard,
    posted_message_tracker: PostedMessageTracker,
) -> None:
    chores = await RemoveChoreUseCase(uow=uow_factory())(RemoveChoreCommand(chore_id=callback_data.chore_id))
    await callback.answer()
    await posted_message_tracker.clear_one(CHORE_DEADLINE_KIND, str(callback_data.chore_id))
    await delete_quietly(callback.message)
    await chores_board.refresh(chores)


@router.callback_query(ChoreCallback.filter(F.action == ChoreAction.RENAME))
async def rename_chore(
    callback: CallbackQuery,
    callback_data: ChoreCallback,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    await callback.answer()
    chore = await _find_chore(callback_data.chore_id, uow_factory)
    await delete_quietly(callback.message)
    prompt = await callback.message.answer(
        messages.CHORES_ASK_NEW_NAME.format(name=chore.name if chore else ""), disable_notification=True
    )
    await state.set_state(ChoreStates.new_name)
    await state.update_data(chore_id=callback_data.chore_id)
    await remember_transient_message(state, prompt)


@router.callback_query(ChoreCallback.filter(F.action == ChoreAction.DEADLINE))
async def ask_deadline(
    callback: CallbackQuery,
    callback_data: ChoreCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    await delete_quietly(callback.message)
    prompt = await callback.message.answer(messages.CHORES_ASK_DEADLINE, disable_notification=True)
    await state.set_state(ChoreStates.new_deadline)
    await state.update_data(chore_id=callback_data.chore_id)
    await remember_transient_message(state, prompt)


@router.callback_query(ChoreCallback.filter(F.action == ChoreAction.ASSIGN_MENU))
async def show_assignee_menu(
    callback: CallbackQuery,
    callback_data: ChoreCallback,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    members = await ListFamilyMembersUseCase(uow=uow_factory())()
    if not members:
        # the roster fills itself from who writes, so early on it can be empty — say so rather than show nothing
        await callback.answer(messages.CHORES_ASSIGN_NO_ROSTER, show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=build_chore_assignee_keyboard(callback_data.chore_id, members)
    )


@router.callback_query(ChoreCallback.filter(F.action == ChoreAction.ASSIGN))
async def set_assignee(
    callback: CallbackQuery,
    callback_data: ChoreCallback,
    uow_factory: Callable[[], UnitOfWork],
    chores_board: ChoresBoard,
) -> None:
    assignee_id: int | None = callback_data.assignee_id or None
    assignee_name: str | None = None
    if assignee_id is not None:
        members = await ListFamilyMembersUseCase(uow=uow_factory())()
        member = next((candidate for candidate in members if candidate.telegram_user_id == assignee_id), None)
        # the roster could have changed between drawing the picker and the tap; a vanished member clears the tag
        assignee_id = member.telegram_user_id if member else None
        assignee_name = member.first_name if member else None

    chores = await SetChoreAssigneeUseCase(uow=uow_factory())(
        SetChoreAssigneeCommand(
            chore_id=callback_data.chore_id,
            assignee_telegram_user_id=assignee_id,
            assignee_display_name=assignee_name,
        )
    )
    await callback.answer(messages.CHORES_ASSIGNED_TOAST if assignee_id else messages.CHORES_UNASSIGNED_TOAST)
    await delete_quietly(callback.message)
    await chores_board.refresh(chores)


@router.callback_query(ChoreCallback.filter(F.action == ChoreAction.DISMISS))
async def dismiss_chore_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await delete_quietly(callback.message)


async def _find_chore(chore_id: int, uow_factory: Callable[[], UnitOfWork]):
    chores = await RetrieveChoresUseCase(uow=uow_factory())()
    return next((chore for chore in chores.open_chores if chore.id == chore_id), None)
