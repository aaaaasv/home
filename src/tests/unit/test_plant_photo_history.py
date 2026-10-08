import unittest
from datetime import datetime, timezone

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
    def setUp(self):
        self.calendar = FrozenHouseholdCalendar(KYIV, FROZEN_NOW)
        self.photo = build_photo(1, 1, PlantPhotoFrame.OVERVIEW)

    def test_render_history_caption_for_the_first_frame_names_the_plant(self):
        caption = render_history_caption("Містер Біг", self.photo, 0, self.calendar)

        self.assertEqual(caption, "<b>Містер Біг</b> · 1 липня, 13:00")

    def test_render_history_caption_for_a_later_frame_is_the_moment_alone(self):
        caption = render_history_caption("Містер Біг", self.photo, 1, self.calendar)

        self.assertEqual(caption, "1 липня, 13:00")

    def test_render_history_caption_escapes_a_name_with_markup_in_it(self):
        caption = render_history_caption("Фікус <b>", self.photo, 0, self.calendar)

        self.assertEqual(caption, "<b>Фікус &lt;b&gt;</b> · 1 липня, 13:00")


if __name__ == "__main__":
    unittest.main()
