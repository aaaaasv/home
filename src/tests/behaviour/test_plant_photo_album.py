import asyncio
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
        """Every frame at once, the way telegram delivers an album, then wait for the session to close itself."""
        # long enough that the quiet interval cannot expire between two frames of the same album, which in
        # life it never does — telegram sends them milliseconds apart — and short enough not to slow the suite
        with patch.object(photos, "ALBUM_SETTLE_SECONDS", 0.05):
            await asyncio.gather(
                *(
                    self.feed(photo_update(unique_id, update_id=index + 10))
                    for index, unique_id in enumerate(unique_ids)
                )
            )
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
            [photo.frame for photo in saved],
            [
                PlantPhotoFrame.OVERVIEW.value,
                PlantPhotoFrame.DETAIL.value,
                PlantPhotoFrame.DETAIL.value,
                PlantPhotoFrame.DETAIL.value,
            ],
        )

    async def test_add_photo_with_an_album_reports_the_number_of_frames_it_saved(self):
        await self.feed_album("first", "second", "third", "fourth")

        self.assertEqual(self.session.sent_texts()[-1], messages.PHOTOS_ADDED.format(count=4))

    async def test_add_photo_with_a_single_frame_reports_one_photo_added(self):
        await self.feed_album("only")

        self.assertEqual(self.session.sent_texts()[-1], messages.PHOTO_ADDED)
