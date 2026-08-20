from collections.abc import Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.plants import messages
from src.bot.handlers.plants.formatting import render_schedule_remove_confirm
from src.bot.handlers.plants.keyboards import (
    CUSTOM_INTERVAL_MARKER,
    ScheduleAction,
    ScheduleCallback,
    build_schedule_interval_keyboard,
    build_schedule_remove_keyboard,
    build_task_type_keyboard,
)
from src.bot.handlers.plants.plant_list import send_plant_card
from src.bot.message_cleanup import delete_quietly, remember_transient_message, sweep_transient_messages
from src.common.constants import CARE_INSTRUCTIONS_MAX_LENGTH, CareTaskType
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import (
    RemoveCareScheduleCommand,
    SetCareInstructionsCommand,
    SetCareScheduleCommand,
)
from src.modules.plant_care.services.care_input_parser import parse_interval_days
from src.modules.plant_care.use_cases.remove_care_schedule import RemoveCareScheduleUseCase
from src.modules.plant_care.use_cases.retrieve_plant_card import RetrievePlantCardUseCase
from src.modules.plant_care.use_cases.set_care_instructions import SetCareInstructionsUseCase
from src.modules.plant_care.use_cases.set_care_schedule import SetCareScheduleUseCase

router = Router(name="schedules")


class SetCareScheduleStates(StatesGroup):
    custom_interval = State()
    instructions = State()


@router.callback_query(ScheduleCallback.filter(F.action == ScheduleAction.CHOOSE_TASK))
async def choose_task_type(
    callback: CallbackQuery,
    callback_data: ScheduleCallback,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    await callback.answer()
    card = await RetrievePlantCardUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        callback_data.plant_id
    )
    await callback.message.answer(messages.ASK_TASK_TYPE, reply_markup=build_task_type_keyboard(card))


@router.callback_query(ScheduleCallback.filter(F.action == ScheduleAction.CHOOSE_INTERVAL))
async def choose_interval(callback: CallbackQuery, callback_data: ScheduleCallback) -> None:
    await callback.answer()
    # the task picker has been answered — replace it with the interval picker rather than stack a second menu
    await delete_quietly(callback.message)
    await callback.message.answer(
        messages.ASK_TASK_INTERVAL,
        reply_markup=build_schedule_interval_keyboard(callback_data.plant_id, callback_data.task_type),
    )


@router.callback_query(ScheduleCallback.filter(F.action == ScheduleAction.SET))
async def set_schedule(
    callback: CallbackQuery,
    callback_data: ScheduleCallback,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    if callback_data.interval_days == CUSTOM_INTERVAL_MARKER:
        await callback.answer()
        await delete_quietly(callback.message)
        await state.set_state(SetCareScheduleStates.custom_interval)
        await state.update_data(plant_id=callback_data.plant_id, task_type=callback_data.task_type)
        prompt = await callback.message.answer(messages.ASK_CUSTOM_TASK_INTERVAL)
        await remember_transient_message(state, prompt)
        return

    await _set_care_schedule(
        plant_id=callback_data.plant_id,
        task_type=callback_data.task_type,
        interval_days=callback_data.interval_days,
        uow_factory=uow_factory,
        household_calendar=household_calendar,
    )
    await callback.answer(messages.CARE_RECORDED_TOAST)
    await delete_quietly(callback.message)
    await _resend_plant_card(callback.message, callback_data.plant_id, uow_factory, household_calendar)


@router.message(SetCareScheduleStates.custom_interval, F.text)
async def store_custom_interval(
    message: Message,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    interval_days = parse_interval_days(message.text)
    if interval_days is None:
        await message.answer(messages.INVALID_INTERVAL)
        return

    collected_data = await state.get_data()
    await state.clear()

    await _set_care_schedule(
        plant_id=collected_data["plant_id"],
        task_type=collected_data["task_type"],
        interval_days=interval_days,
        uow_factory=uow_factory,
        household_calendar=household_calendar,
    )
    await delete_quietly(message)
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await _resend_plant_card(message, collected_data["plant_id"], uow_factory, household_calendar)


@router.callback_query(ScheduleCallback.filter(F.action == ScheduleAction.EDIT_INSTRUCTIONS))
async def edit_instructions(callback: CallbackQuery, callback_data: ScheduleCallback, state: FSMContext) -> None:
    await callback.answer()
    await delete_quietly(callback.message)
    await state.set_state(SetCareScheduleStates.instructions)
    await state.update_data(plant_id=callback_data.plant_id, task_type=callback_data.task_type)
    prompt = await callback.message.answer(messages.ASK_CARE_INSTRUCTIONS)
    await remember_transient_message(state, prompt)


@router.message(SetCareScheduleStates.instructions, F.text)
async def store_instructions(
    message: Message,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    text = message.text.strip()
    instructions = None if text == "/clear" else text
    if instructions is not None and len(instructions) > CARE_INSTRUCTIONS_MAX_LENGTH:
        await message.answer(messages.CARE_INSTRUCTIONS_TOO_LONG)
        return

    collected_data = await state.get_data()
    await state.clear()

    await SetCareInstructionsUseCase(uow=uow_factory())(
        SetCareInstructionsCommand(
            plant_id=collected_data["plant_id"], task_type=collected_data["task_type"], instructions=instructions
        )
    )
    await delete_quietly(message)
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await _resend_plant_card(message, collected_data["plant_id"], uow_factory, household_calendar)


@router.callback_query(ScheduleCallback.filter(F.action == ScheduleAction.CONFIRM_REMOVE))
async def confirm_remove_schedule(
    callback: CallbackQuery,
    callback_data: ScheduleCallback,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    card = await RetrievePlantCardUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        callback_data.plant_id
    )
    schedule = next(item for item in card.schedules if item.task_type == callback_data.task_type)

    await callback.answer()
    await delete_quietly(callback.message)
    await callback.message.answer(
        render_schedule_remove_confirm(card.name, schedule),
        reply_markup=build_schedule_remove_keyboard(callback_data.plant_id, callback_data.task_type),
    )


@router.callback_query(ScheduleCallback.filter(F.action == ScheduleAction.REMOVE))
async def remove_schedule(
    callback: CallbackQuery,
    callback_data: ScheduleCallback,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    await RemoveCareScheduleUseCase(uow=uow_factory())(
        RemoveCareScheduleCommand(plant_id=callback_data.plant_id, task_type=callback_data.task_type)
    )
    await callback.answer()
    await delete_quietly(callback.message)
    await _resend_plant_card(callback.message, callback_data.plant_id, uow_factory, household_calendar)


async def _set_care_schedule(
    plant_id: int,
    task_type: CareTaskType,
    interval_days: int,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    await SetCareScheduleUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        SetCareScheduleCommand(plant_id=plant_id, task_type=task_type, interval_days=interval_days)
    )


async def _resend_plant_card(
    message: Message,
    plant_id: int,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    card = await RetrievePlantCardUseCase(uow=uow_factory(), household_calendar=household_calendar)(plant_id)
    await send_plant_card(message, card, household_calendar)
