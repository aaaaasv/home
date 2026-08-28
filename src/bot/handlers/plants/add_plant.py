from collections.abc import Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.plants import messages
from src.bot.handlers.plants.keyboards import (
    CUSTOM_INTERVAL_MARKER,
    NewPlantIntervalCallback,
    build_new_plant_interval_keyboard,
)
from src.bot.handlers.plants.plant_list import send_plant_card
from src.bot.message_cleanup import (
    delete_message_quietly,
    delete_quietly,
    remember_transient_message,
    replace_prompt,
    sweep_transient_messages,
)
from src.common.constants import PLANT_NAME_MAX_LENGTH, CareTaskType
from src.common.domain import Actor
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import CreatePlantCommand, SetCareInstructionsCommand, TelegramPhoto
from src.modules.plant_care.services.care_input_parser import parse_interval_days
from src.modules.plant_care.services.photo_storage import PhotoStorage
from src.modules.plant_care.services.plant_identifier import PlantIdentifier
from src.modules.plant_care.use_cases.create_plant import CreatePlantUseCase
from src.modules.plant_care.use_cases.set_care_instructions import SetCareInstructionsUseCase

router = Router(name="add_plant")


class AddPlantStates(StatesGroup):
    name = State()
    photo = State()
    watering_interval = State()
    custom_watering_interval = State()


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
async def store_photo(
    message: Message,
    state: FSMContext,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    photo_storage: PhotoStorage,
    plant_identifier: PlantIdentifier | None = None,
) -> None:
    largest_photo = message.photo[-1]
    await state.update_data(
        photo_file_id=largest_photo.file_id,
        photo_file_unique_id=largest_photo.file_unique_id,
        photo_caption=message.caption,
    )
    await delete_quietly(message)
    if plant_identifier is None:
        await _ask_watering_interval(message, state)
        return

    await _identify_and_create(
        message, state, plant_identifier, largest_photo.file_id, actor, uow_factory, household_calendar, photo_storage
    )


async def _identify_and_create(
    message: Message,
    state: FSMContext,
    plant_identifier: PlantIdentifier,
    file_id: str,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    photo_storage: PhotoStorage,
) -> None:
    """
    Names the plant from its photo and offers the answer for confirmation.

    a refusal is a normal outcome, not a failure: a young cutting or a bad light genuinely cannot be named, and
    saying so costs one message, while a confident wrong species would be copied into the card and believed.
    """
    thinking = await message.answer(messages.ADD_PLANT_IDENTIFYING)
    downloaded = await message.bot.download(file_id)
    identification = await plant_identifier.identify(downloaded.read())
    if identification is None:
        await thinking.edit_text(messages.ADD_PLANT_IDENTIFICATION_UNSURE)
        await remember_transient_message(state, thinking)
        await _ask_watering_interval(message, state)
        return

    await state.update_data(
        species=identification.species,
        care_notes=identification.care_notes,
    )
    await delete_message_quietly(message.bot, message.chat.id, thinking.message_id)
    if identification.watering_interval_days is None:
        # a name without a rhythm is not enough to make a plant, so the one open question is still asked
        await _ask_watering_interval(message, state)
        return

    await state.update_data(watering_interval_days=identification.watering_interval_days)
    await _create_plant(
        message, state, actor, uow_factory, household_calendar, photo_storage, note=messages.ADD_PLANT_FROM_PHOTO
    )


@router.message(AddPlantStates.photo, Command("skip"))
async def skip_photo(message: Message, state: FSMContext) -> None:
    await delete_quietly(message)
    await _ask_watering_interval(message, state)


@router.message(AddPlantStates.photo)
async def reject_non_photo(message: Message, state: FSMContext) -> None:
    await delete_quietly(message)
    await _ask(message, state, messages.ADD_PLANT_EXPECTS_PHOTO)


@router.callback_query(AddPlantStates.watering_interval, NewPlantIntervalCallback.filter())
async def store_watering_interval(
    callback: CallbackQuery,
    callback_data: NewPlantIntervalCallback,
    state: FSMContext,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    photo_storage: PhotoStorage,
) -> None:
    await callback.answer()
    if callback_data.interval_days == CUSTOM_INTERVAL_MARKER:
        await state.set_state(AddPlantStates.custom_watering_interval)
        await _ask(callback.message, state, messages.ADD_PLANT_ASK_CUSTOM_INTERVAL)
        return

    await state.update_data(watering_interval_days=callback_data.interval_days)
    await _create_plant(callback.message, state, actor, uow_factory, household_calendar, photo_storage)


@router.message(AddPlantStates.custom_watering_interval, F.text)
async def store_custom_watering_interval(
    message: Message,
    state: FSMContext,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    photo_storage: PhotoStorage,
) -> None:
    interval_days = parse_interval_days(message.text)
    await delete_quietly(message)
    if interval_days is None:
        await _ask(message, state, messages.INVALID_INTERVAL)
        return

    await state.update_data(watering_interval_days=interval_days)
    await _create_plant(message, state, actor, uow_factory, household_calendar, photo_storage)


async def _create_plant(
    message: Message,
    state: FSMContext,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    photo_storage: PhotoStorage,
    note: str | None = None,
) -> None:
    """
    Makes the plant the moment the wizard knows a name and a rhythm, which is everything it cannot invent.

    the species, the place and the notes are whatever the photo gave — all three are edited on the finished
    card, so none of them is worth a question. the first watering is not asked either: a new plant comes out
    due today, and the card carries a «полито» button for the case where it was watered on the way home.
    """
    collected_data = await state.get_data()
    await state.clear()

    use_case = CreatePlantUseCase(
        uow=uow_factory(), actor=actor, household_calendar=household_calendar, photo_storage=photo_storage
    )
    card = await use_case(
        CreatePlantCommand(
            name=collected_data["name"],
            species=collected_data.get("species"),
            photo=_build_photo(collected_data),
            watering_interval_days=collected_data["watering_interval_days"],
        )
    )
    care_notes = collected_data.get("care_notes")
    if care_notes is not None:
        await SetCareInstructionsUseCase(uow=uow_factory())(
            SetCareInstructionsCommand(plant_id=card.id, task_type=CareTaskType.WATERING, instructions=care_notes)
        )
    # the whole wizard collapses to the one thing worth keeping — the finished card
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    if note is not None:
        await message.answer(note)
    await send_plant_card(message, card, household_calendar)


async def _ask(message: Message, state: FSMContext, text: str) -> None:
    prompt = await message.answer(text)
    await replace_prompt(state, prompt)


async def _ask_photo(message: Message, state: FSMContext) -> None:
    await state.set_state(AddPlantStates.photo)
    await _ask(message, state, messages.ADD_PLANT_ASK_PHOTO)


async def _ask_watering_interval(message: Message, state: FSMContext) -> None:
    await state.set_state(AddPlantStates.watering_interval)
    prompt = await message.answer(messages.ADD_PLANT_ASK_INTERVAL, reply_markup=build_new_plant_interval_keyboard())
    await replace_prompt(state, prompt)


def _build_photo(collected_data: dict) -> TelegramPhoto | None:
    if "photo_file_id" not in collected_data:
        return None
    return TelegramPhoto(
        file_id=collected_data["photo_file_id"],
        file_unique_id=collected_data["photo_file_unique_id"],
        caption=collected_data.get("photo_caption"),
    )
