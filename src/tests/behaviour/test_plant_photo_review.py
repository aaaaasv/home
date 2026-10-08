from unittest.mock import patch

from src.bot.handlers.plants import messages, photos
from src.bot.handlers.plants.keyboards import PlantAction, PlantCallback
from src.common.constants import PlantPhotoReviewStatus
from src.modules.plant_care.domain import PlantPhotoReview
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.fakes import RecordingPhotoAnalyst
from src.tests.telegram import ACTOR_ID, CHAT_ID, callback_update, photo_update

REVIEW = PlantPhotoReview(status=PlantPhotoReviewStatus.OK, summary="Виглядає здоровою.", change=None, action=None)


class PhotoReviewFailureTestCase(BaseBehaviourTestCase):
    """
    What the group sees when the model cannot answer.

    it used to see «фото додано» and then nothing at all, because the «дивлюсь» placeholder was deleted — which
    is exactly what the bot ignoring the upload looks like. three photos in a row looked that way on 7 october.
    """

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Містер Біг")
        async with self.uow as uow:
            await uow.family_members.upsert(ACTOR_ID, "Тест")

    async def upload_a_photo(self, analyst) -> None:
        await self.feed(
            callback_update(PlantCallback(action=PlantAction.ADD_PHOTO, plant_id=self.plant_id).pack()),
            photo_analyst=analyst,
        )
        with patch.object(photos, "ALBUM_SETTLE_SECONDS", 0.05):
            await self.feed(photo_update("only", update_id=10), photo_analyst=analyst)
            await photos._open_sessions[(CHAT_ID, ACTOR_ID)].closing

    async def test_a_review_that_cannot_be_made_says_so_instead_of_vanishing(self):
        await self.upload_a_photo(RecordingPhotoAnalyst(review=None))

        edits = self.session.calls_named("EditMessageText")
        self.assertEqual([call.text for call in edits], [messages.PHOTO_REVIEW_FAILED])
        # the «надішли фото» prompt is swept as usual; what must survive is the placeholder carrying the answer
        deleted = [call.message_id for call in self.session.calls_named("DeleteMessage")]
        self.assertNotIn(edits[0].message_id, deleted)

    async def test_a_review_that_cannot_be_made_offers_to_look_again(self):
        await self.upload_a_photo(RecordingPhotoAnalyst(review=None))

        edited = self.session.calls_named("EditMessageText")[-1]
        self.assertEqual(
            [button.text for row in edited.reply_markup.inline_keyboard for button in row],
            [messages.PHOTO_REVIEW_RETRY_BUTTON],
        )

    async def test_a_review_that_succeeds_carries_no_retry_button(self):
        await self.upload_a_photo(RecordingPhotoAnalyst(review=REVIEW))

        edited = self.session.calls_named("EditMessageText")[-1]
        self.assertEqual(edited.text, "✅ Виглядає здоровою.")
        self.assertIsNone(edited.reply_markup)

    async def test_tapping_look_again_replaces_the_failure_with_the_review(self):
        await self.upload_a_photo(RecordingPhotoAnalyst(review=None))
        self.session.calls.clear()

        await self.feed(
            callback_update(PlantCallback(action=PlantAction.REVIEW_PHOTO, plant_id=self.plant_id).pack()),
            photo_analyst=RecordingPhotoAnalyst(review=REVIEW),
        )

        self.assertEqual(
            [call.text for call in self.session.calls_named("EditMessageText")],
            [messages.PHOTO_REVIEW_IN_PROGRESS, "✅ Виглядає здоровою."],
        )

    async def test_tapping_look_again_while_it_still_cannot_be_made_keeps_the_offer(self):
        await self.upload_a_photo(RecordingPhotoAnalyst(review=None))
        self.session.calls.clear()

        await self.feed(
            callback_update(PlantCallback(action=PlantAction.REVIEW_PHOTO, plant_id=self.plant_id).pack()),
            photo_analyst=RecordingPhotoAnalyst(review=None),
        )

        edited = self.session.calls_named("EditMessageText")[-1]
        self.assertEqual(edited.text, messages.PHOTO_REVIEW_FAILED)
        self.assertEqual(
            [button.text for row in edited.reply_markup.inline_keyboard for button in row],
            [messages.PHOTO_REVIEW_RETRY_BUTTON],
        )

    async def test_tapping_look_again_with_no_model_configured_says_nothing(self):
        await self.upload_a_photo(RecordingPhotoAnalyst(review=None))
        self.session.calls.clear()

        await self.feed(callback_update(PlantCallback(action=PlantAction.REVIEW_PHOTO, plant_id=self.plant_id).pack()))

        self.assertEqual(self.session.calls_named("EditMessageText"), [])
