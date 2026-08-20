from collections.abc import Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.plants import messages
from src.bot.handlers.plants.keyboards import EditPlantCallback, PlantAction, PlantCallback, build_plant_edit_keyboard
from src.bot.handlers.plants.plant_list import send_plant_card
from src.bot.message_cleanup import delete_quietly, remember_transient_message, sweep_transient_messages
from src.common.constants import (
    CLIMATE_FIELD_BOUNDS,
    CLIMATE_FIELD_COLUMNS,
    PLANT_CLIMATE_FIELDS,
    PLANT_FIELD_MAX_LENGTHS,
    PlantField,
)
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import UpdatePlantCommand
from src.modules.plant_care.services.care_input_parser import parse_climate_range
from src.modules.plant_care.use_cases.retrieve_plant_card import RetrievePlantCardUseCase
from src.modules.plant_care.use_cases.update_plant import UpdatePlantUseCase

router = Router(name="edit_plant")


class EditPlantStates(StatesGroup):
    field_value = State()


@router.callback_query(PlantCallback.filter(F.action == PlantAction.EDIT))
async def choose_field(
    callback: CallbackQuery,
    callback_data: PlantCallback,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    await callback.answer()
    card = await RetrievePlantCardUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        callback_data.plant_id
    )
    await callback.message.answer(messages.ASK_EDIT_FIELD, reply_markup=build_plant_edit_keyboard(card))


@router.callback_query(EditPlantCallback.filter())
async def ask_new_value(callback: CallbackQuery, callback_data: EditPlantCallback, state: FSMContext) -> None:
    await callback.answer()
    # the field picker has done its job — drop it so only the card and the one prompt remain
    await delete_quietly(callback.message)
    await state.set_state(EditPlantStates.field_value)
    await state.update_data(plant_id=callback_data.plant_id, field=callback_data.field)
    prompt = await callback.message.answer(messages.EDIT_FIELD_PROMPTS[callback_data.field])
    await remember_transient_message(state, prompt)


@router.message(EditPlantStates.field_value, Command("clear"))
async def clear_field(
    message: Message,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    collected_data = await state.get_data()
    field = collected_data["field"]
    if field == PlantField.NAME:
        await message.answer(messages.NAME_CANNOT_BE_CLEARED)
        return

    await state.clear()
    if field in PLANT_CLIMATE_FIELDS:
        minimum_column, maximum_column = CLIMATE_FIELD_COLUMNS[field]
        changes = {minimum_column: None, maximum_column: None}
    else:
        changes = {field: None}
    await delete_quietly(message)
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await _apply_changes(message, collected_data["plant_id"], changes, uow_factory, household_calendar)


@router.message(EditPlantStates.field_value, F.text)
async def store_new_value(
    message: Message,
    state: FSMContext,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    collected_data = await state.get_data()
    field = collected_data["field"]

    if field in PLANT_CLIMATE_FIELDS:
        parsed_range = parse_climate_range(message.text, *CLIMATE_FIELD_BOUNDS[field])
        if parsed_range is None:
            await message.answer(messages.CLIMATE_RANGE_INVALID)
            return
        minimum_column, maximum_column = CLIMATE_FIELD_COLUMNS[field]
        changes = {minimum_column: parsed_range[0], maximum_column: parsed_range[1]}
    else:
        new_value = message.text.strip()
        max_length = PLANT_FIELD_MAX_LENGTHS[field]
        if len(new_value) > max_length:
            await message.answer(messages.EDIT_VALUE_TOO_LONG.format(max_length=max_length))
            return
        changes = {field: new_value}

    await state.clear()
    await delete_quietly(message)
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await _apply_changes(message, collected_data["plant_id"], changes, uow_factory, household_calendar)


async def _apply_changes(
    message: Message,
    plant_id: int,
    changes: dict,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    command = UpdatePlantCommand(plant_id=plant_id, **changes)

    await UpdatePlantUseCase(uow=uow_factory())(command)

    card = await RetrievePlantCardUseCase(uow=uow_factory(), household_calendar=household_calendar)(plant_id)
    await send_plant_card(message, card, household_calendar)
