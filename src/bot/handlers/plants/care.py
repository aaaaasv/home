from collections.abc import Callable

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from src.bot.formatting import exceeds_caption_limit, format_day
from src.bot.handlers.plants import messages
from src.bot.handlers.plants.formatting import (
    render_care_card_caption,
    render_care_history,
    render_recent_care_warning,
    render_recorded_care,
)
from src.bot.handlers.plants.keyboards import (
    CareCallback,
    ScheduleAction,
    ScheduleCallback,
    build_care_card_keyboard,
    build_care_cards,
    build_force_care_keyboard,
    build_recorded_care_keyboard,
)
from src.bot.services.posted_message_tracker import CARE_DIGEST_KIND, PostedMessageTracker, build_care_task_reference
from src.common.config import Settings
from src.common.constants import CareTaskType
from src.common.domain import Actor
from src.common.exceptions import RecentCareExistsError
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import PostponeCareTaskCommand, RecordCareEventCommand, UndoCareEventCommand
from src.modules.plant_care.use_cases.build_care_digest import BuildCareDigestUseCase
from src.modules.plant_care.use_cases.list_care_history import ListCareHistoryUseCase
from src.modules.plant_care.use_cases.postpone_care_task import PostponeCareTaskUseCase
from src.modules.plant_care.use_cases.record_care_event import RecordCareEventUseCase
from src.modules.plant_care.use_cases.undo_care_event import UndoCareEventUseCase

router = Router(name="care")


@router.message(Command("today"))
async def show_today(
    message: Message, uow_factory: Callable[[], UnitOfWork], household_calendar: HouseholdCalendar
) -> None:
    digest = await BuildCareDigestUseCase(uow=uow_factory(), household_calendar=household_calendar)()
    if not digest.tasks:
        await message.answer(messages.NOTHING_DUE)
        return

    for card in build_care_cards(digest):
        if card.photo_file_id is None or exceeds_caption_limit(card.caption):
            if card.photo_file_id is not None:
                await message.answer_photo(card.photo_file_id)
            await message.answer(card.caption, reply_markup=card.keyboard)
        else:
            await message.answer_photo(card.photo_file_id, caption=card.caption, reply_markup=card.keyboard)


@router.message(Command("history"))
async def show_history(
    message: Message, uow_factory: Callable[[], UnitOfWork], household_calendar: HouseholdCalendar
) -> None:
    entries = await ListCareHistoryUseCase(uow=uow_factory())()
    if not entries:
        await message.answer(messages.NO_HISTORY)
        return

    await message.answer(render_care_history(entries, household_calendar))


@router.callback_query(CareCallback.filter())
async def record_care(
    callback: CallbackQuery,
    callback_data: CareCallback,
    actor: Actor,
    settings: Settings,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    posted_message_tracker: PostedMessageTracker,
) -> None:
    use_case = RecordCareEventUseCase(
        uow=uow_factory(),
        actor=actor,
        household_calendar=household_calendar,
        recent_care_guard_hours=settings.RECENT_CARE_GUARD_HOURS,
    )
    performed_at = household_calendar.now()
    command = RecordCareEventCommand(
        plant_id=callback_data.plant_id,
        task_type=callback_data.task_type,
        performed_at=performed_at,
        force=callback_data.force,
    )

    try:
        record = await use_case(command)
    except RecentCareExistsError as recent_care:
        await callback.answer()
        await callback.message.answer(
            render_recent_care_warning(
                plant_name=recent_care.plant_name,
                task_type=recent_care.task_type,
                performed_at=recent_care.performed_at,
                performed_by_display_name=recent_care.performed_by_display_name,
                calendar=household_calendar,
            ),
            reply_markup=build_force_care_keyboard(callback_data.plant_id, callback_data.task_type),
        )
        return

    await callback.answer(messages.CARE_RECORDED_TOAST)
    # the card stays, but as a receipt: no record button to tap twice, and an undo for the tap that was a mistake
    await _rewrite_card(
        callback.message,
        render_recorded_care(record, performed_at, household_calendar),
        build_recorded_care_keyboard(callback_data.plant_id, callback_data.task_type),
    )
    await _drop_digest_card(
        posted_message_tracker, callback_data.plant_id, callback_data.task_type, callback.message.message_id
    )


@router.callback_query(ScheduleCallback.filter(F.action == ScheduleAction.UNDO))
async def undo_care(
    callback: CallbackQuery,
    callback_data: ScheduleCallback,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    task = await UndoCareEventUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        UndoCareEventCommand(plant_id=callback_data.plant_id, task_type=callback_data.task_type)
    )

    await callback.answer(messages.CARE_UNDONE_TOAST)
    # back to a due card, so the task can be done for real without waiting for tomorrow's digest
    await _rewrite_card(callback.message, render_care_card_caption(task), build_care_card_keyboard(task))


@router.callback_query(ScheduleCallback.filter(F.action == ScheduleAction.POSTPONE))
async def postpone_care(
    callback: CallbackQuery,
    callback_data: ScheduleCallback,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    posted_message_tracker: PostedMessageTracker,
) -> None:
    postponed = await PostponeCareTaskUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        PostponeCareTaskCommand(
            plant_id=callback_data.plant_id,
            task_type=callback_data.task_type,
            postponed_at=household_calendar.now(),
        )
    )

    await callback.answer(
        messages.CARE_POSTPONED_TOAST.format(when=format_day(postponed.next_due_on, household_calendar.today()))
    )
    await _delete_quietly(callback.message)
    await _drop_digest_card(posted_message_tracker, callback_data.plant_id, callback_data.task_type)


async def _drop_digest_card(
    posted_message_tracker: PostedMessageTracker,
    plant_id: int,
    task_type: CareTaskType,
    keep_message_id: int | None = None,
) -> None:
    # the action may have come from the plant card, which leaves the digest card standing on a settled task
    await posted_message_tracker.clear_one(
        CARE_DIGEST_KIND, build_care_task_reference(plant_id, task_type), keep_message_id=keep_message_id
    )


async def _rewrite_card(message: Message, text: str, keyboard: InlineKeyboardMarkup) -> None:
    # a digest card carries the plant's photo, so its text lives in the caption rather than in the body
    if message.photo:
        await message.edit_caption(caption=text, reply_markup=keyboard)
    else:
        await message.edit_text(text, reply_markup=keyboard)


async def _delete_quietly(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
