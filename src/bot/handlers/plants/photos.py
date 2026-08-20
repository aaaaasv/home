from collections.abc import Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from src.bot.formatting import format_moment
from src.bot.handlers.plants import messages
from src.bot.handlers.plants.formatting import render_plant_photo_review
from src.bot.handlers.plants.keyboards import PlantAction, PlantCallback
from src.bot.message_cleanup import (
    delete_message_quietly,
    delete_quietly,
    remember_transient_message,
    sweep_transient_messages,
)
from src.common.domain import Actor
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import AddPlantPhotoCommand, TelegramPhoto
from src.modules.plant_care.services.photo_analyst import PhotoAnalyst
from src.modules.plant_care.services.photo_storage import PhotoStorage
from src.modules.plant_care.use_cases.add_plant_photo import AddPlantPhotoUseCase
from src.modules.plant_care.use_cases.list_plant_photos import ListPlantPhotosUseCase
from src.modules.plant_care.use_cases.review_plant_photo import ReviewPlantPhotoUseCase

router = Router(name="photos")

TIMELINE_PHOTO_LIMIT = 10


class AddPhotoStates(StatesGroup):
    photo = State()


@router.callback_query(PlantCallback.filter(F.action == PlantAction.ADD_PHOTO))
async def ask_for_photo(callback: CallbackQuery, callback_data: PlantCallback, state: FSMContext) -> None:
    await _start_upload(callback, callback_data.plant_id, state, due_card_message_id=None)


@router.callback_query(PlantCallback.filter(F.action == PlantAction.ADD_PHOTO_DUE))
async def ask_for_due_photo(callback: CallbackQuery, callback_data: PlantCallback, state: FSMContext) -> None:
    # remember the digest card so the arriving photo can drop it, the way recording care drops its own card
    await _start_upload(callback, callback_data.plant_id, state, due_card_message_id=callback.message.message_id)


async def _start_upload(
    callback: CallbackQuery, plant_id: int, state: FSMContext, due_card_message_id: int | None
) -> None:
    await callback.answer()
    await state.set_state(AddPhotoStates.photo)
    await state.update_data(plant_id=plant_id, due_card_message_id=due_card_message_id)
    prompt = await callback.message.answer(messages.ADD_PHOTO_ASK_PHOTO)
    await remember_transient_message(state, prompt)


@router.message(AddPhotoStates.photo, F.photo)
async def add_photo(
    message: Message,
    state: FSMContext,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    photo_storage: PhotoStorage,
    photo_analyst: PhotoAnalyst | None,
) -> None:
    collected_data = await state.get_data()
    await state.clear()

    largest_photo = message.photo[-1]
    plant_id = collected_data["plant_id"]
    use_case = AddPlantPhotoUseCase(
        uow=uow_factory(), actor=actor, photo_storage=photo_storage, household_calendar=household_calendar
    )
    await use_case(
        AddPlantPhotoCommand(
            plant_id=plant_id,
            photo=TelegramPhoto(
                file_id=largest_photo.file_id,
                file_unique_id=largest_photo.file_unique_id,
                caption=message.caption,
            ),
            taken_at=household_calendar.now(),
        )
    )
    await _drop_due_card(message, collected_data.get("due_card_message_id"))
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await message.answer(messages.PHOTO_ADDED)
    await _review_photo(message, plant_id, uow_factory, household_calendar, photo_analyst)


async def _review_photo(
    message: Message,
    plant_id: int,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    photo_analyst: PhotoAnalyst | None,
) -> None:
    if photo_analyst is None:
        return

    # the model takes a while to answer, so say it is looking rather than leave the upload hanging in silence
    notice = await message.answer(messages.PHOTO_REVIEW_IN_PROGRESS)
    use_case = ReviewPlantPhotoUseCase(
        uow=uow_factory(), household_calendar=household_calendar, photo_analyst=photo_analyst
    )
    review = await use_case(plant_id)
    if review is None:
        await delete_quietly(notice)
        return

    await notice.edit_text(render_plant_photo_review(review))


async def _drop_due_card(message: Message, due_card_message_id: int | None) -> None:
    if due_card_message_id is None:
        return

    # the card may be older than telegram's edit window, or already gone — the photo is saved either way
    await delete_message_quietly(message.bot, message.chat.id, due_card_message_id)


@router.message(AddPhotoStates.photo)
async def reject_non_photo(message: Message) -> None:
    await message.answer(messages.ADD_PLANT_EXPECTS_PHOTO)


@router.callback_query(PlantCallback.filter(F.action == PlantAction.PHOTOS))
async def show_photo_timeline(
    callback: CallbackQuery,
    callback_data: PlantCallback,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    await callback.answer()
    photos = await ListPlantPhotosUseCase(uow=uow_factory())(callback_data.plant_id)
    if not photos:
        await callback.message.answer(messages.NO_PHOTOS)
        return

    timeline = photos[-TIMELINE_PHOTO_LIMIT:]
    await callback.message.answer_media_group(
        [
            InputMediaPhoto(
                media=photo.telegram_file_id,
                caption=format_moment(photo.taken_at, household_calendar),
            )
            for photo in timeline
        ]
    )
