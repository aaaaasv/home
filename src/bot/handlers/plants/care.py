from collections.abc import Callable

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from src.bot.formatting import exceeds_caption_limit, format_day
from src.bot.handlers.plants import messages
from src.bot.handlers.plants.care_card_reference import build_care_card_reference
from src.bot.handlers.plants.care_cards import (
    build_care_cards_for_digest,
    build_plant_care_card,
    refresh_care_cards,
    retarget_care_card,
)
from src.bot.handlers.plants.formatting import (
    render_care_history,
    render_plant_card,
    render_postponements,
    render_recent_care_warning,
    render_recorded_care,
)
from src.bot.handlers.plants.keyboards import (
    CareCallback,
    ScheduleAction,
    ScheduleCallback,
    build_care_cards,
    build_force_care_keyboard,
    build_plant_card_keyboard,
    build_recorded_care_keyboard,
    find_recorded_task_types,
)
from src.bot.handlers.plants.plant_list import send_plant_card
from src.bot.message_cleanup import delete_quietly
from src.common.config import Settings
from src.common.domain import Actor
from src.common.exceptions import RecentCareExistsError
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import PostponeCareTaskCommand, RecordCareEventCommand, UndoCareEventCommand
from src.modules.plant_care.domain import CareDigest
from src.modules.plant_care.use_cases.build_care_digest import BuildCareDigestUseCase
from src.modules.plant_care.use_cases.list_care_history import ListCareHistoryUseCase
from src.modules.plant_care.use_cases.postpone_care_task import PostponeCareTaskUseCase
from src.modules.plant_care.use_cases.record_care_event import RecordCareEventUseCase
from src.modules.plant_care.use_cases.retrieve_plant_card import RetrievePlantCardUseCase
from src.modules.plant_care.use_cases.undo_care_event import UndoCareEventUseCase

router = Router(name="care")


@router.message(Command("today"))
async def show_today(
    message: Message, uow_factory: Callable[[], UnitOfWork], household_calendar: HouseholdCalendar, settings: Settings
) -> None:
    digest = await BuildCareDigestUseCase(uow=uow_factory(), household_calendar=household_calendar)()
    if not digest.tasks:
        await message.answer(messages.NOTHING_DUE)
        return

    for card in await build_care_cards_for_digest(uow_factory, household_calendar, settings, digest):
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
    bot: Bot,
    actor: Actor,
    settings: Settings,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
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
            reply_markup=build_force_care_keyboard(
                callback_data.plant_id, callback_data.task_type, from_plant_card=callback_data.from_plant_card
            ),
        )
        return

    await callback.answer(messages.CARE_RECORDED_TOAST)
    if callback_data.from_plant_card:
        await _redraw_plant_card(callback, callback_data, settings, uow_factory, household_calendar)
        await refresh_care_cards(bot, uow_factory, household_calendar, settings, callback_data.plant_id)
        return

    # a forced record is confirmed from the warning, so the card the person tapped is not the message under the tap
    card_is_under_tap = not callback_data.force
    remaining_card = await build_plant_care_card(uow_factory, household_calendar, settings, callback_data.plant_id)
    if card_is_under_tap and remaining_card is not None:
        await _rewrite_card(callback.message, remaining_card.caption, remaining_card.keyboard)
        await retarget_care_card(uow_factory, callback.message.message_id, remaining_card.reference)
    else:
        # nothing else is due, so the card stays as a receipt: no record button to tap twice, and an undo for
        # the tap that was a mistake
        await _rewrite_card(
            callback.message,
            render_recorded_care(record, performed_at, household_calendar),
            build_recorded_care_keyboard(callback_data.plant_id, callback_data.task_type),
        )
        await retarget_care_card(
            uow_factory, callback.message.message_id, build_care_card_reference(callback_data.plant_id, ())
        )
    await refresh_care_cards(
        bot,
        uow_factory,
        household_calendar,
        settings,
        callback_data.plant_id,
        except_message_id=callback.message.message_id if card_is_under_tap else None,
    )


@router.callback_query(ScheduleCallback.filter(F.action == ScheduleAction.UNDO))
async def undo_care(
    callback: CallbackQuery,
    callback_data: ScheduleCallback,
    bot: Bot,
    settings: Settings,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    task = await UndoCareEventUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        UndoCareEventCommand(plant_id=callback_data.plant_id, task_type=callback_data.task_type)
    )

    await callback.answer(messages.CARE_UNDONE_TOAST)
    # back to a due card, so the task can be done for real without waiting for tomorrow's digest
    card = await build_plant_care_card(uow_factory, household_calendar, settings, callback_data.plant_id)
    if card is None:
        card = build_care_cards(CareDigest(today=household_calendar.today(), tasks=[task]))[0]
    await _rewrite_card(callback.message, card.caption, card.keyboard)
    await retarget_care_card(uow_factory, callback.message.message_id, card.reference)
    await refresh_care_cards(
        bot,
        uow_factory,
        household_calendar,
        settings,
        callback_data.plant_id,
        except_message_id=callback.message.message_id,
    )


@router.callback_query(ScheduleCallback.filter(F.action == ScheduleAction.POSTPONE))
async def postpone_care(
    callback: CallbackQuery,
    callback_data: ScheduleCallback,
    bot: Bot,
    settings: Settings,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    postponed = await PostponeCareTaskUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        PostponeCareTaskCommand(
            plant_id=callback_data.plant_id,
            task_type=callback_data.task_type,
            postponed_at=household_calendar.now(),
        )
    )

    toast = messages.CARE_POSTPONED_TOAST.format(when=format_day(postponed.next_due_on, household_calendar.today()))
    again = render_postponements(postponed.consecutive_postponements)
    await callback.answer(f"{toast} · {again}" if again else toast)
    remaining_card = await build_plant_care_card(uow_factory, household_calendar, settings, callback_data.plant_id)
    if remaining_card is None:
        await delete_quietly(callback.message)
    else:
        await _rewrite_card(callback.message, remaining_card.caption, remaining_card.keyboard)
        await retarget_care_card(uow_factory, callback.message.message_id, remaining_card.reference)
    await refresh_care_cards(
        bot,
        uow_factory,
        household_calendar,
        settings,
        callback_data.plant_id,
        except_message_id=callback.message.message_id if remaining_card is not None else None,
    )


async def _redraw_plant_card(
    callback: CallbackQuery,
    callback_data: CareCallback,
    settings: Settings,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    """The page somebody opened stays a page: the same data, newer, so the next due date and the history are true."""
    card = await RetrievePlantCardUseCase(
        uow=uow_factory(), household_calendar=household_calendar, sensor_by_plant=settings.sensor_by_plant
    )(callback_data.plant_id)
    if callback_data.force:
        # the message under the tap is the warning, not the page, so the page goes out again below it
        await delete_quietly(callback.message)
        await send_plant_card(callback.message, card, household_calendar)
        return

    recorded_task_types = find_recorded_task_types(card, callback.message.reply_markup) | {callback_data.task_type}
    await _rewrite_card(
        callback.message,
        render_plant_card(card, household_calendar),
        build_plant_card_keyboard(card, recorded_task_types),
    )


async def _rewrite_card(message: Message, text: str, keyboard: InlineKeyboardMarkup) -> None:
    # a digest card carries the plant's photo, so its text lives in the caption rather than in the body
    if message.photo:
        await message.edit_caption(caption=text, reply_markup=keyboard)
    else:
        await message.edit_text(text, reply_markup=keyboard)
