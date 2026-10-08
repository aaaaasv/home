import unittest
from datetime import datetime, timezone

from src.bot.handlers.plants.keyboards import PhotoHistoryCallback, build_photo_history_keyboard
from src.bot.handlers.plants.photos import build_photo_history, render_history_caption
from src.common.constants import PlantPhotoFrame
from src.modules.plant_care.domain import PlantPhotoDetails
from src.tests.fakes import FrozenHouseholdCalendar
from src.tests.integration.base import FROZEN_NOW, KYIV


def build_photo(photo_id: int, day: int, frame: PlantPhotoFrame) -> PlantPhotoDetails:
    return PlantPhotoDetails(
        id=photo_id,
        telegram_file_id=f"file-{photo_id}",
        caption=None,
        taken_at=datetime(2026, 7, day, 10, 0, tzinfo=timezone.utc),
        frame=frame,
    )


class BuildPhotoHistoryTestCase(unittest.TestCase):
    """The card's album is the plant's growth: one frame per sitting, the newest one first."""

    def test_build_photo_history_keeps_only_the_general_frames(self):
        photos = [
            build_photo(1, 1, PlantPhotoFrame.OVERVIEW),
            build_photo(2, 1, PlantPhotoFrame.DETAIL),
            build_photo(3, 5, PlantPhotoFrame.OVERVIEW),
        ]

        history = build_photo_history(photos)

        self.assertEqual([photo.id for photo in history], [3, 1])

    def test_build_photo_history_puts_the_newest_sitting_first(self):
        photos = [build_photo(index, index, PlantPhotoFrame.OVERVIEW) for index in range(1, 4)]

        history = build_photo_history(photos)

        self.assertEqual([photo.id for photo in history], [3, 2, 1])

    def test_build_photo_history_of_a_collection_past_the_album_limit_keeps_the_ten_newest(self):
        photos = [build_photo(index, index, PlantPhotoFrame.OVERVIEW) for index in range(1, 15)]

        history = build_photo_history(photos)

        self.assertEqual([photo.id for photo in history], [14, 13, 12, 11, 10, 9, 8, 7, 6, 5])

    def test_build_photo_history_with_no_general_frame_at_all_is_empty(self):
        history = build_photo_history([build_photo(1, 1, PlantPhotoFrame.DETAIL)])

        self.assertEqual(history, [])


class RenderHistoryCaptionTestCase(unittest.TestCase):
    """Every frame stands alone: the card scrolls away from the one it was opened from."""

    def setUp(self):
        self.calendar = FrozenHouseholdCalendar(KYIV, FROZEN_NOW)
        self.photo = build_photo(1, 1, PlantPhotoFrame.OVERVIEW)

    def test_render_history_caption_names_the_plant_the_moment_and_the_place_in_the_run(self):
        caption = render_history_caption("Містер Біг", self.photo, 0, 3, self.calendar)

        self.assertEqual(caption, "<b>Містер Біг</b> · 1 липня, 13:00 · 1/3")

    def test_render_history_caption_for_a_later_frame_counts_from_the_newest(self):
        caption = render_history_caption("Містер Біг", self.photo, 2, 3, self.calendar)

        self.assertEqual(caption, "<b>Містер Біг</b> · 1 липня, 13:00 · 3/3")

    def test_render_history_caption_escapes_a_name_with_markup_in_it(self):
        caption = render_history_caption("Фікус <b>", self.photo, 0, 1, self.calendar)

        self.assertEqual(caption, "<b>Фікус &lt;b&gt;</b> · 1 липня, 13:00 · 1/1")


class BuildPhotoHistoryKeyboardTestCase(unittest.TestCase):
    def labels(self, index: int, total: int) -> list[str]:
        keyboard = build_photo_history_keyboard(plant_id=7, index=index, total=total)
        if keyboard is None:
            return []
        return [button.text for row in keyboard.inline_keyboard for button in row]

    def test_the_newest_frame_can_only_step_back_in_time(self):
        self.assertEqual(self.labels(index=0, total=3), ["старіше →"])

    def test_a_middle_frame_steps_both_ways(self):
        self.assertEqual(self.labels(index=1, total=3), ["← новіше", "старіше →"])

    def test_the_oldest_frame_can_only_step_forward(self):
        self.assertEqual(self.labels(index=2, total=3), ["← новіше"])

    def test_a_single_sitting_carries_no_buttons_at_all(self):
        self.assertIsNone(build_photo_history_keyboard(plant_id=7, index=0, total=1))

    def test_a_step_payload_stays_well_under_the_telegram_limit(self):
        packed = PhotoHistoryCallback(plant_id=999999, index=9).pack()

        self.assertLessEqual(len(packed.encode()), 64)


if __name__ == "__main__":
    unittest.main()
