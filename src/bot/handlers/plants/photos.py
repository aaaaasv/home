import asyncio
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
from src.common.constants import PlantPhotoFrame
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
# an album's frames land milliseconds apart; this is how long the session waits for another one
ALBUM_SETTLE_SECONDS = 2.0

# one open photo session per person per chat, kept here because an asyncio task cannot live in fsm data
_open_sessions: dict[tuple[int, int], asyncio.Task] = {}


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
    """
    Saves one frame of a photo session, which may be a whole album.

    the care instruction asks for a general frame and then close-ups of the leaves, in that order, so the first
    frame of a session is the one growth is measured against and the rest are evidence. the state is deliberately
    not cleared here: telegram delivers an album as separate messages, and clearing on the first would drop the
    rest of it in silence.
    """
    collected_data = await state.get_data()
    frames_saved = collected_data.get("frames_saved", 0)
    plant_id = collected_data["plant_id"]

    largest_photo = message.photo[-1]
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
            frame=PlantPhotoFrame.OVERVIEW if frames_saved == 0 else PlantPhotoFrame.DETAIL,
        )
    )
    await state.update_data(frames_saved=frames_saved + 1)
    _restart_session_timer(message, state, plant_id, collected_data, uow_factory, household_calendar, photo_analyst)


def _restart_session_timer(
    message: Message,
    state: FSMContext,
    plant_id: int,
    collected_data: dict,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    photo_analyst: PhotoAnalyst | None,
) -> None:
    # there is no "album finished" update, so the session closes a moment after frames stop arriving; each new
    # frame pushes the deadline back, and a lone photo simply waits out one quiet interval
    key = (message.chat.id, message.from_user.id)
    pending = _open_sessions.pop(key, None)
    if pending is not None:
        pending.cancel()

    async def close_when_quiet() -> None:
        await asyncio.sleep(ALBUM_SETTLE_SECONDS)
        _open_sessions.pop(key, None)
        saved = (await state.get_data()).get("frames_saved", 1)
        await state.clear()
        await _drop_due_card(message, collected_data.get("due_card_message_id"))
        await sweep_transient_messages(message.bot, message.chat.id, collected_data)
        await message.answer(messages.PHOTO_ADDED if saved == 1 else messages.PHOTOS_ADDED.format(count=saved))
        await _review_photo(message, plant_id, uow_factory, household_calendar, photo_analyst)

    _open_sessions[key] = asyncio.create_task(close_when_quiet())


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


# last of the photo handlers, so it only sees what no upload flow claimed: a photo dropped into the topic by
# itself, or the tail of an album whose first frame already finished its flow. either way it must not vanish
@router.message(F.photo)
async def explain_a_stray_photo(message: Message) -> None:
    """A photo nobody asked for used to disappear without a word, which reads exactly like the bot losing it."""
    await message.answer(messages.STRAY_PHOTO)


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
