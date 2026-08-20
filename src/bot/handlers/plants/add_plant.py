from collections.abc import Callable
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.plants import messages
from src.bot.handlers.plants.keyboards import (
    CUSTOM_INTERVAL_MARKER,
    UNKNOWN_LAST_WATERED_MARKER,
    NewPlantIntervalCallback,
    NewPlantLastWateredCallback,
    build_new_plant_interval_keyboard,
    build_new_plant_last_watered_keyboard,
)
from src.bot.handlers.plants.plant_list import send_plant_card
from src.bot.message_cleanup import delete_quietly, replace_prompt, sweep_transient_messages
from src.common.constants import PLANT_NAME_MAX_LENGTH
from src.common.domain import Actor
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import CreatePlantCommand, TelegramPhoto
from src.modules.plant_care.services.care_input_parser import parse_interval_days
from src.modules.plant_care.services.photo_storage import PhotoStorage
from src.modules.plant_care.use_cases.create_plant import CreatePlantUseCase

router = Router(name="add_plant")


class AddPlantStates(StatesGroup):
    name = State()
    photo = State()
    species = State()
    location = State()
    watering_interval = State()
    custom_watering_interval = State()
    last_watered = State()


@router.message(Command("add"))
async def start_adding_plant(message: Message, state: FSMContext) -> None:
    await delete_quietly(message)
    await state.set_state(AddPlantStates.name)
    await _ask(message, state, messages.ADD_PLANT_ASK_NAME)


@router.message(AddPlantStates.name, F.text)
async def store_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    await delete_quietly(message)
    if len(name) > PLANT_NAME_MAX_LENGTH:
        await _ask(message, state, messages.ADD_PLANT_NAME_TOO_LONG)
        return

    await state.update_data(name=name)
    await _ask_photo(message, state)


@router.message(AddPlantStates.photo, F.photo)
async def store_photo(message: Message, state: FSMContext) -> None:
    largest_photo = message.photo[-1]
    await state.update_data(
        photo_file_id=largest_photo.file_id,
        photo_file_unique_id=largest_photo.file_unique_id,
        photo_caption=message.caption,
    )
    await delete_quietly(message)
    await _ask_species(message, state)


@router.message(AddPlantStates.photo, Command("skip"))
async def skip_photo(message: Message, state: FSMContext) -> None:
    await delete_quietly(message)
    await _ask_species(message, state)


@router.message(AddPlantStates.photo)
async def reject_non_photo(message: Message, state: FSMContext) -> None:
    await delete_quietly(message)
    await _ask(message, state, messages.ADD_PLANT_EXPECTS_PHOTO)


@router.message(AddPlantStates.species, Command("skip"))
async def skip_species(message: Message, state: FSMContext) -> None:
    await delete_quietly(message)
    await _ask_location(message, state)


@router.message(AddPlantStates.species, F.text)
async def store_species(message: Message, state: FSMContext) -> None:
    await state.update_data(species=message.text.strip())
    await delete_quietly(message)
    await _ask_location(message, state)


@router.message(AddPlantStates.location, Command("skip"))
async def skip_location(message: Message, state: FSMContext) -> None:
    await delete_quietly(message)
    await _ask_watering_interval(message, state)


@router.message(AddPlantStates.location, F.text)
async def store_location(message: Message, state: FSMContext) -> None:
    await state.update_data(location=message.text.strip())
    await delete_quietly(message)
    await _ask_watering_interval(message, state)


@router.callback_query(AddPlantStates.watering_interval, NewPlantIntervalCallback.filter())
async def store_watering_interval(
    callback: CallbackQuery, callback_data: NewPlantIntervalCallback, state: FSMContext
) -> None:
    await callback.answer()
    if callback_data.interval_days == CUSTOM_INTERVAL_MARKER:
        await state.set_state(AddPlantStates.custom_watering_interval)
        await _ask(callback.message, state, messages.ADD_PLANT_ASK_CUSTOM_INTERVAL)
        return

    await state.update_data(watering_interval_days=callback_data.interval_days)
    await _ask_last_watered(callback.message, state)


@router.message(AddPlantStates.custom_watering_interval, F.text)
async def store_custom_watering_interval(message: Message, state: FSMContext) -> None:
    interval_days = parse_interval_days(message.text)
    await delete_quietly(message)
    if interval_days is None:
        await _ask(message, state, messages.INVALID_INTERVAL)
        return

    await state.update_data(watering_interval_days=interval_days)
    await _ask_last_watered(message, state)


@router.callback_query(AddPlantStates.last_watered, NewPlantLastWateredCallback.filter())
async def create_plant(
    callback: CallbackQuery,
    callback_data: NewPlantLastWateredCallback,
    state: FSMContext,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    photo_storage: PhotoStorage,
) -> None:
    await callback.answer()
    collected_data = await state.get_data()
    await state.clear()

    use_case = CreatePlantUseCase(
        uow=uow_factory(), actor=actor, household_calendar=household_calendar, photo_storage=photo_storage
    )
    card = await use_case(
        CreatePlantCommand(
            name=collected_data["name"],
            species=collected_data.get("species"),
            location=collected_data.get("location"),
            photo=_build_photo(collected_data),
            watering_interval_days=collected_data["watering_interval_days"],
            last_watered_on=_resolve_last_watered_on(callback_data.days_ago, household_calendar),
        )
    )
    # the whole wizard collapses to the one thing worth keeping — the finished card
    await sweep_transient_messages(callback.message.bot, callback.message.chat.id, collected_data)
    await send_plant_card(callback.message, card, household_calendar)


async def _ask(message: Message, state: FSMContext, text: str) -> None:
    prompt = await message.answer(text)
    await replace_prompt(state, prompt)


async def _ask_photo(message: Message, state: FSMContext) -> None:
    await state.set_state(AddPlantStates.photo)
    await _ask(message, state, messages.ADD_PLANT_ASK_PHOTO)


async def _ask_species(message: Message, state: FSMContext) -> None:
    await state.set_state(AddPlantStates.species)
    await _ask(message, state, messages.ADD_PLANT_ASK_SPECIES)


async def _ask_location(message: Message, state: FSMContext) -> None:
    await state.set_state(AddPlantStates.location)
    await _ask(message, state, messages.ADD_PLANT_ASK_LOCATION)


async def _ask_watering_interval(message: Message, state: FSMContext) -> None:
    await state.set_state(AddPlantStates.watering_interval)
    prompt = await message.answer(messages.ADD_PLANT_ASK_INTERVAL, reply_markup=build_new_plant_interval_keyboard())
    await replace_prompt(state, prompt)


async def _ask_last_watered(message: Message, state: FSMContext) -> None:
    await state.set_state(AddPlantStates.last_watered)
    prompt = await message.answer(
        messages.ADD_PLANT_ASK_LAST_WATERED, reply_markup=build_new_plant_last_watered_keyboard()
    )
    await replace_prompt(state, prompt)


def _build_photo(collected_data: dict) -> TelegramPhoto | None:
    if "photo_file_id" not in collected_data:
        return None
    return TelegramPhoto(
        file_id=collected_data["photo_file_id"],
        file_unique_id=collected_data["photo_file_unique_id"],
        caption=collected_data.get("photo_caption"),
    )


def _resolve_last_watered_on(days_ago: int, household_calendar: HouseholdCalendar) -> date | None:
    if days_ago == UNKNOWN_LAST_WATERED_MARKER:
        return None
    return household_calendar.today() - timedelta(days=days_ago)
