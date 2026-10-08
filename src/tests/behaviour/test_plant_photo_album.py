from datetime import datetime, timezone
from unittest.mock import patch

from src.bot.handlers.plants import messages, photos
from src.bot.handlers.plants.keyboards import PlantAction, PlantCallback
from src.common.constants import PlantPhotoFrame
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.telegram import ACTOR_ID, CHAT_ID, callback_update, photo_update


class PlantPhotoAlbumTestCase(BaseBehaviourTestCase):
    """
    An album driven the way telegram delivers one: several updates at once, not one after another.

    fed sequentially every one of these passes even against the racing version, which is how four frames
    reached production as one saved frame and three «Щось пішло не так».
    """

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Містер Біг")
        # already on the roster, as anyone sending their tenth photo is — otherwise the four updates race to
        # add the same person and the roster middleware fails three of them before the photos are even reached
        async with self.uow as uow:
            await uow.family_members.upsert(ACTOR_ID, "Тест")
        await self.feed(callback_update(PlantCallback(action=PlantAction.ADD_PHOTO, plant_id=self.plant_id).pack()))
        self.session.calls.clear()

    async def feed_album(self, *unique_ids: str) -> None:
        """
        One frame after another, then wait for the session to close itself.

        telegram sends an album's frames milliseconds apart, but it sends them as separate updates and the
        dispatcher takes them one at a time — so feeding them concurrently was not faithful, and it raced:
        four frames gathered at once arrived in whatever order the loop happened to schedule, and the test
        failed roughly once in three runs on the order alone.
        """
        # long enough that the quiet interval cannot expire between two frames, short enough not to slow the suite
        with patch.object(photos, "ALBUM_SETTLE_SECONDS", 0.5):
            for index, unique_id in enumerate(unique_ids):
                await self.feed(photo_update(unique_id, update_id=index + 10))
            await photos._open_sessions[(CHAT_ID, ACTOR_ID)].closing

    async def test_add_photo_with_an_album_of_four_frames_saves_every_frame(self):
        await self.feed_album("first", "second", "third", "fourth")

        async with self.uow as uow:
            saved = await uow.plant_photos.list_by_plant_id(self.plant_id)

        self.assertEqual([photo.telegram_file_unique_id for photo in saved], ["first", "second", "third", "fourth"])

    async def test_add_photo_with_an_album_marks_only_the_first_frame_as_the_overview(self):
        await self.feed_album("first", "second", "third", "fourth")

        async with self.uow as uow:
            saved = await uow.plant_photos.list_by_plant_id(self.plant_id)

        self.assertEqual(
            {photo.telegram_file_unique_id: photo.frame for photo in saved},
            {
                "first": PlantPhotoFrame.OVERVIEW.value,
                "second": PlantPhotoFrame.DETAIL.value,
                "third": PlantPhotoFrame.DETAIL.value,
                "fourth": PlantPhotoFrame.DETAIL.value,
            },
        )

    async def test_add_photo_with_an_album_whose_first_frame_is_handled_last_still_marks_it_the_overview(self):
        # the order production once saw: the album's first message reached the lock after the second one
        with patch.object(photos, "ALBUM_SETTLE_SECONDS", 0.05):
            await self.feed(photo_update("second", update_id=11))
            await self.feed(photo_update("first", update_id=10))
            await photos._open_sessions[(CHAT_ID, ACTOR_ID)].closing

        async with self.uow as uow:
            saved = await uow.plant_photos.list_by_plant_id(self.plant_id)

        self.assertEqual(
            {photo.telegram_file_unique_id: photo.frame for photo in saved},
            {"first": PlantPhotoFrame.OVERVIEW.value, "second": PlantPhotoFrame.DETAIL.value},
        )

    async def test_add_photo_with_an_album_reports_the_number_of_frames_it_saved(self):
        await self.feed_album("first", "second", "third", "fourth")

        self.assertEqual(self.session.sent_texts()[-1], messages.PHOTOS_ADDED.format(count=4))

    async def test_add_photo_with_a_single_frame_reports_one_photo_added(self):
        await self.feed_album("only")

        self.assertEqual(self.session.sent_texts()[-1], messages.PHOTO_ADDED)


class StragglingAlbumFrameTestCase(BaseBehaviourTestCase):
    """
    A frame that reached the bot after its album had been closed off.

    there is no "album finished" update, so the session closes after a couple of quiet seconds. a frame held up
    past that — a slow upload, or the bot waiting on sqlite's write lock — used to be answered «натисни 📸 на
    картці» and never stored at all.
    """

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Містер Біг")
        async with self.uow as uow:
            await uow.family_members.upsert(ACTOR_ID, "Тест")
        await self.feed(callback_update(PlantCallback(action=PlantAction.ADD_PHOTO, plant_id=self.plant_id).pack()))
        self.session.calls.clear()
        photos._closed_albums.clear()
        self.addCleanup(photos._closed_albums.clear)

    async def upload_album(self, *unique_ids: str, media_group_id: str = "album-1") -> None:
        with patch.object(photos, "ALBUM_SETTLE_SECONDS", 0.05):
            for index, unique_id in enumerate(unique_ids):
                await self.feed(photo_update(unique_id, update_id=index + 10, media_group_id=media_group_id))
            await photos._open_sessions[(CHAT_ID, ACTOR_ID)].closing

    async def saved_frames(self) -> dict[str, str]:
        async with self.uow as uow:
            return {
                photo.telegram_file_unique_id: photo.frame
                for photo in await uow.plant_photos.list_by_plant_id(self.plant_id)
            }

    async def test_a_frame_arriving_after_its_album_closed_is_stored_on_the_same_plant(self):
        await self.upload_album("first", "second")

        await self.feed(photo_update("late", update_id=20, media_group_id="album-1"))

        self.assertEqual(
            await self.saved_frames(),
            {
                "first": PlantPhotoFrame.OVERVIEW.value,
                "second": PlantPhotoFrame.DETAIL.value,
                "late": PlantPhotoFrame.DETAIL.value,
            },
        )

    async def test_a_frame_arriving_after_its_album_closed_says_it_joined_the_collection(self):
        await self.upload_album("first", "second")
        self.session.calls.clear()

        await self.feed(photo_update("late", update_id=20, media_group_id="album-1"))

        self.assertEqual(self.session.sent_texts(), [messages.PHOTO_ADDED_LATE])

    async def test_a_frame_of_a_different_album_is_still_refused_as_a_stray_photo(self):
        await self.upload_album("first", "second")
        self.session.calls.clear()

        await self.feed(photo_update("other", update_id=20, media_group_id="album-2"))

        self.assertEqual(self.session.sent_texts(), [messages.STRAY_PHOTO])
        self.assertNotIn("other", await self.saved_frames())

    async def test_a_lone_photo_with_no_album_is_still_refused_as_a_stray_photo(self):
        await self.upload_album("first", "second")
        self.session.calls.clear()

        await self.feed(photo_update("lone", update_id=20))

        self.assertEqual(self.session.sent_texts(), [messages.STRAY_PHOTO])
        self.assertNotIn("lone", await self.saved_frames())

    async def test_a_frame_arriving_long_after_its_album_closed_is_refused_as_a_stray_photo(self):
        await self.upload_album("first", "second")
        self.session.calls.clear()

        with patch.object(photos, "STRAGGLER_GRACE_SECONDS", -1.0):
            await self.feed(photo_update("late", update_id=20, media_group_id="album-1"))

        self.assertEqual(self.session.sent_texts(), [messages.STRAY_PHOTO])
        self.assertNotIn("late", await self.saved_frames())


class PhotoHistoryCarouselTestCase(BaseBehaviourTestCase):
    """
    The card's photo button opens the plant's growth as one album, which telegram swipes through natively.

    it used to hand over the last ten frames of any kind in the order they were taken, so the close-ups of one
    afternoon buried the one thing the album is for: the plant then and now.
    """

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Містер Біг")

    async def open_history(self):
        return await self.feed(callback_update(PlantCallback(action=PlantAction.PHOTOS, plant_id=self.plant_id).pack()))

    async def seed_frame(self, unique_id: str, day: int, frame: PlantPhotoFrame) -> None:
        await self.seed_plant_photo(
            plant_id=self.plant_id,
            telegram_file_id=f"file-{unique_id}",
            telegram_file_unique_id=unique_id,
            frame=frame.value,
            taken_at=datetime(2026, 7, day, 10, 0, tzinfo=timezone.utc),
        )

    async def test_opening_the_history_sends_the_general_frames_newest_first(self):
        await self.seed_frame("july-first", 1, PlantPhotoFrame.OVERVIEW)
        await self.seed_frame("july-first-close-up", 1, PlantPhotoFrame.DETAIL)
        await self.seed_frame("july-fifth", 5, PlantPhotoFrame.OVERVIEW)

        await self.open_history()

        sent = self.session.calls_named("SendMediaGroup")
        self.assertEqual(len(sent), 1)
        self.assertEqual([item.media for item in sent[0].media], ["file-july-fifth", "file-july-first"])

    async def test_opening_the_history_names_the_plant_on_the_first_frame_only(self):
        await self.seed_frame("july-first", 1, PlantPhotoFrame.OVERVIEW)
        await self.seed_frame("july-fifth", 5, PlantPhotoFrame.OVERVIEW)

        await self.open_history()

        sent = self.session.calls_named("SendMediaGroup")
        self.assertEqual(
            [item.caption for item in sent[0].media],
            ["<b>Містер Біг</b> · 5 липня, 13:00", "1 липня, 13:00"],
        )

    async def test_opening_the_history_of_a_plant_with_no_photos_says_so(self):
        await self.open_history()

        self.assertEqual(self.session.calls_named("SendMediaGroup"), [])
        self.assertEqual(self.session.sent_texts(), [messages.NO_PHOTOS])

    async def test_the_card_button_counts_the_sittings_the_album_holds(self):
        await self.seed_frame("july-first", 1, PlantPhotoFrame.OVERVIEW)
        await self.seed_frame("july-first-close-up", 1, PlantPhotoFrame.DETAIL)
        await self.seed_frame("july-fifth", 5, PlantPhotoFrame.OVERVIEW)

        await self.feed(callback_update(PlantCallback(action=PlantAction.OPEN, plant_id=self.plant_id).pack()))

        buttons = [
            button.text
            for call in self.session.calls
            if getattr(call, "reply_markup", None) is not None
            for row in call.reply_markup.inline_keyboard
            for button in row
        ]
        self.assertIn("Історія (2)", buttons)
