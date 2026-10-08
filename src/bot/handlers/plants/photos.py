import asyncio
import time
from collections.abc import Callable
from html import escape
from typing import NamedTuple

from aiogram import F, Router
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from src.bot.formatting import format_moment
from src.bot.handlers.plants import messages
from src.bot.handlers.plants.care_cards import refresh_care_cards
from src.bot.handlers.plants.formatting import render_plant_photo_review
from src.bot.handlers.plants.keyboards import PlantAction, PlantCallback
from src.bot.message_cleanup import delete_quietly, remember_transient_message, sweep_transient_messages
from src.common.config import Settings
from src.common.constants import PlantPhotoFrame
from src.common.domain import Actor
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import AddPlantPhotoCommand, TelegramPhoto
from src.modules.plant_care.domain import PlantPhotoDetails
from src.modules.plant_care.services.photo_analyst import PhotoAnalyst
from src.modules.plant_care.services.photo_storage import PhotoStorage
from src.modules.plant_care.use_cases.add_plant_photo import AddPlantPhotoUseCase
from src.modules.plant_care.use_cases.list_plant_photos import ListPlantPhotosUseCase
from src.modules.plant_care.use_cases.retrieve_plant_card import RetrievePlantCardUseCase
from src.modules.plant_care.use_cases.review_plant_photo import ReviewPlantPhotoUseCase

router = Router(name="photos")

TIMELINE_PHOTO_LIMIT = 10
# an album's frames land milliseconds apart; this is how long the session waits for another one
ALBUM_SETTLE_SECONDS = 2.0
# how long a finished album still takes in a frame that only now arrived
STRAGGLER_GRACE_SECONDS = 180.0


class PhotoSession:
    """
    One person's upload in one chat, which telegram may deliver as an album of several updates.

    the frames are saved one at a time. run concurrently they each read the frame count before any of them
    writes it, so every frame calls itself the first, and they contend for sqlite's single write lock until
    all but one is lost — three of four frames once disappeared that way, with an error apiece.
    """

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.frames_arriving = 0
        self.closing: asyncio.Task | None = None
        # the message id and saved photo id of the frame currently marked as the overview
        self.overview: tuple[int, int] | None = None
        # the albums this session has taken frames from, so a straggler can be recognised after it closes
        self.media_group_ids: set[str] = set()


class ClosedAlbum(NamedTuple):
    plant_id: int
    closed_at: float


# one open photo session per person per chat, kept here because neither a lock nor a task can live in fsm data
_open_sessions: dict[tuple[int, int], PhotoSession] = {}
# albums whose session has already closed. there is no "album finished" update, so the session closes after a
# couple of quiet seconds — and a frame delayed past that (a slow upload, or the bot held up by sqlite's write
# lock) used to be refused as a stray photo and lost without a trace. it is still the same album, so it is
# still the same plant
_closed_albums: dict[tuple[int, int, str], ClosedAlbum] = {}


class AddPhotoStates(StatesGroup):
    photo = State()


# the digest card's button is a separate action only because cards posted before the two flows merged still carry it
@router.callback_query(PlantCallback.filter(F.action.in_({PlantAction.ADD_PHOTO, PlantAction.ADD_PHOTO_DUE})))
async def ask_for_photo(callback: CallbackQuery, callback_data: PlantCallback, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AddPhotoStates.photo)
    await state.update_data(plant_id=callback_data.plant_id)
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
    settings: Settings,
    photo_analyst: PhotoAnalyst | None,
) -> None:
    """
    Saves one frame of a photo session, which may be a whole album.

    the care instruction asks for a general frame and then close-ups of the leaves, in that order, so the first
    frame of an album is the one growth is measured against and the rest are evidence. first means first in the
    album, not first saved: the frames arrive as separate updates handled at once, and whichever reaches the lock
    first is often not the one the person put first — a close-up once became the overview that way. the message
    id carries the album's own order, so a frame older than the current overview takes the overview over.

    the state is deliberately not cleared here: telegram delivers an album as separate messages, and clearing on
    the first would drop the rest of it in silence.
    """
    key = (message.chat.id, message.from_user.id)
    session = _open_sessions.setdefault(key, PhotoSession())
    # claimed before the first await, so a session still filling can never be closed out from under this frame
    session.frames_arriving += 1
    _cancel_closing(session)

    try:
        async with session.lock:
            collected_data = await state.get_data()
            frames_saved = collected_data.get("frames_saved", 0)

            largest_photo = message.photo[-1]
            is_earliest_frame = session.overview is None or message.message_id < session.overview[0]
            use_case = AddPlantPhotoUseCase(
                uow=uow_factory(), actor=actor, photo_storage=photo_storage, household_calendar=household_calendar
            )
            saved = await use_case(
                AddPlantPhotoCommand(
                    plant_id=collected_data["plant_id"],
                    photo=TelegramPhoto(
                        file_id=largest_photo.file_id,
                        file_unique_id=largest_photo.file_unique_id,
                        caption=message.caption,
                    ),
                    taken_at=household_calendar.now(),
                    frame=PlantPhotoFrame.OVERVIEW if is_earliest_frame else PlantPhotoFrame.DETAIL,
                    supersedes_overview_photo_id=session.overview[1]
                    if is_earliest_frame and session.overview
                    else None,
                )
            )
            if is_earliest_frame:
                session.overview = (message.message_id, saved.id)
            if message.media_group_id:
                session.media_group_ids.add(message.media_group_id)
            await state.update_data(frames_saved=frames_saved + 1)
    finally:
        session.frames_arriving -= 1
        if session.frames_arriving == 0:
            _close_when_quiet(message, state, session, uow_factory, household_calendar, settings, photo_analyst)


def _cancel_closing(session: PhotoSession) -> None:
    if session.closing is None:
        return

    session.closing.cancel()
    session.closing = None


def _close_when_quiet(
    message: Message,
    state: FSMContext,
    session: PhotoSession,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    settings: Settings,
    photo_analyst: PhotoAnalyst | None,
) -> None:
    # there is no "album finished" update, so the session closes a moment after frames stop arriving; each new
    # frame pushes the deadline back, and a lone photo simply waits out one quiet interval
    key = (message.chat.id, message.from_user.id)

    async def close_when_quiet() -> None:
        await asyncio.sleep(ALBUM_SETTLE_SECONDS)
        # read after the wait, so the count and the transient messages are whatever the whole album left behind
        session_data = await state.get_data()
        _open_sessions.pop(key, None)
        _remember_closed_albums(key, session, session_data["plant_id"])
        await state.clear()
        saved = session_data.get("frames_saved", 1)
        # the photo settles the plant's photo task, so its reminder card loses the line or goes altogether
        await refresh_care_cards(message.bot, uow_factory, household_calendar, settings, session_data["plant_id"])
        await sweep_transient_messages(message.bot, message.chat.id, session_data)
        await message.answer(messages.PHOTO_ADDED if saved == 1 else messages.PHOTOS_ADDED.format(count=saved))
        await _review_photo(message, session_data["plant_id"], uow_factory, household_calendar, photo_analyst)

    session.closing = asyncio.create_task(close_when_quiet())


def _remember_closed_albums(key: tuple[int, int], session: PhotoSession, plant_id: int) -> None:
    closed_at = time.monotonic()
    for media_group_id in session.media_group_ids:
        _closed_albums[(*key, media_group_id)] = ClosedAlbum(plant_id=plant_id, closed_at=closed_at)
    _forget_stale_albums(closed_at)


def _forget_stale_albums(now: float) -> None:
    for stale in [key for key, album in _closed_albums.items() if now - album.closed_at > STRAGGLER_GRACE_SECONDS]:
        del _closed_albums[stale]


class BelongsToAFinishedAlbum(Filter):
    """Passes a photo whose album this person finished uploading moments ago, and hands the handler its plant."""

    async def __call__(self, message: Message) -> dict[str, int] | bool:
        if not message.media_group_id or message.from_user is None:
            return False
        album = _closed_albums.get((message.chat.id, message.from_user.id, message.media_group_id))
        if album is None or time.monotonic() - album.closed_at > STRAGGLER_GRACE_SECONDS:
            return False
        return {"album_plant_id": album.plant_id}


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


@router.message(AddPhotoStates.photo)
async def reject_non_photo(message: Message) -> None:
    await message.answer(messages.ADD_PLANT_EXPECTS_PHOTO)


# before the stray-photo handler, and outside the flow's state on purpose: this frame arrives after the session
# that owned its album has already closed and cleared the state
@router.message(F.photo, BelongsToAFinishedAlbum())
async def add_a_straggling_album_frame(
    message: Message,
    album_plant_id: int,
    actor: Actor,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    photo_storage: PhotoStorage,
) -> None:
    """
    Takes in a frame that lost its album, rather than refusing it as a stray photo.

    it is always a later frame than the one the overview was chosen from — an album arrives in order — so it
    joins the collection as evidence and the general frame already picked stands.
    """
    largest_photo = message.photo[-1]
    use_case = AddPlantPhotoUseCase(
        uow=uow_factory(), actor=actor, photo_storage=photo_storage, household_calendar=household_calendar
    )
    await use_case(
        AddPlantPhotoCommand(
            plant_id=album_plant_id,
            photo=TelegramPhoto(
                file_id=largest_photo.file_id,
                file_unique_id=largest_photo.file_unique_id,
                caption=message.caption,
            ),
            taken_at=household_calendar.now(),
            frame=PlantPhotoFrame.DETAIL,
        )
    )
    await message.answer(messages.PHOTO_ADDED_LATE)


# last of the photo handlers, so it only sees what no upload flow claimed: a photo dropped into the topic by
# itself. it must not vanish
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
    plant = await RetrievePlantCardUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        callback_data.plant_id
    )
    photos = await ListPlantPhotosUseCase(uow=uow_factory())(callback_data.plant_id)
    history = build_photo_history(photos)
    if not history:
        await callback.message.answer(messages.NO_PHOTOS)
        return

    # telegram opens an album in its own viewer and swipes between its frames, so the album IS the carousel —
    # newest first, because what the plant looks like now is what somebody opening this wants first
    await callback.message.answer_media_group(
        [
            InputMediaPhoto(
                media=photo.telegram_file_id,
                caption=render_history_caption(plant.name, photo, index, household_calendar),
            )
            for index, photo in enumerate(history)
        ]
    )


def build_photo_history(photos: list[PlantPhotoDetails]) -> list[PlantPhotoDetails]:
    """
    One frame per session, newest first — the plant's growth and nothing else.

    the close-ups of a single day are evidence about that day, not history: mixed into the same album they
    bury the one thing the album is for, which is seeing the plant then and now. an album holds ten frames,
    so a collection older than ten sessions shows the ten most recent.
    """
    overviews = [photo for photo in photos if photo.frame == PlantPhotoFrame.OVERVIEW]
    return list(reversed(overviews[-TIMELINE_PHOTO_LIMIT:]))


def render_history_caption(
    plant_name: str, photo: PlantPhotoDetails, index: int, household_calendar: HouseholdCalendar
) -> str:
    """The album scrolls away from the card it was opened from, so the first frame carries the plant's name."""
    moment = format_moment(photo.taken_at, household_calendar)
    return f"<b>{escape(plant_name)}</b> · {moment}" if index == 0 else moment
