import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.bot.handlers.plants.gemini_photo_analyst import RESPONSE_FORMAT_INSTRUCTION, build_review_parts, parse_review
from src.bot.handlers.plants.photo_review_prompt import SYSTEM_PROMPT
from src.common.constants import CareTaskType, PlantPhotoReviewStatus
from src.modules.plant_care.domain import PhotoReviewSchedule, PlantPhotoReviewContext


def make_context(
    current_photo_path: str, previous_photo_path: str | None = None, days_since_previous_photo: int | None = None
) -> PlantPhotoReviewContext:
    return PlantPhotoReviewContext(
        plant_name="Кактус",
        species="Nepenthes",
        location="кухня",
        ideal_temperature_min_celsius=13.0,
        ideal_temperature_max_celsius=33.0,
        ideal_humidity_min_percent=42.0,
        ideal_humidity_max_percent=90.0,
        room_temperature_celsius=27.0,
        room_humidity_percent=39.0,
        schedules=[PhotoReviewSchedule(task_type=CareTaskType.WATERING, interval_days=7, days_since_last_performed=3)],
        current_photo_path=current_photo_path,
        current_photo_taken_on=date(2026, 8, 28),
        previous_photo_path=previous_photo_path,
        previous_photo_taken_on=date(2026, 7, 13) if previous_photo_path else None,
        days_since_previous_photo=days_since_previous_photo,
    )


class ParseReviewTestCase(unittest.TestCase):
    def test_parse_review_reads_a_well_formed_verdict(self):
        text = json.dumps(
            {"status": "watch", "summary": "нижнє листя жовтіє", "change": "жовті листки", "action": "перевір ґрунт"}
        )
        payload = {"candidates": [{"content": {"parts": [{"text": text}]}}]}

        review = parse_review(payload, "Кактус")

        self.assertEqual(review.status, PlantPhotoReviewStatus.WATCH)
        self.assertEqual(review.summary, "нижнє листя жовтіє")
        self.assertEqual(review.change, "жовті листки")
        self.assertEqual(review.action, "перевір ґрунт")

    def test_parse_review_accepts_null_change_and_action(self):
        text = json.dumps({"status": "ok", "summary": "здорова", "change": None, "action": None})
        payload = {"candidates": [{"content": {"parts": [{"text": text}]}}]}

        review = parse_review(payload, "Кактус")

        self.assertEqual(review.status, PlantPhotoReviewStatus.OK)
        self.assertIsNone(review.change)
        self.assertIsNone(review.action)

    def test_parse_review_returns_none_for_unparsable_json(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "вибач, не можу"}]}}]}

        self.assertIsNone(parse_review(payload, "Кактус"))

    def test_parse_review_returns_none_when_there_are_no_candidates(self):
        self.assertIsNone(parse_review({"candidates": []}, "Кактус"))


class BuildReviewPartsTestCase(unittest.TestCase):
    def test_build_review_parts_inlines_the_single_photo_with_the_instruction(self):
        with tempfile.TemporaryDirectory() as directory:
            current_photo_path = Path(directory) / "current.jpg"
            current_photo_path.write_bytes(b"\x00\x01\x02")

            parts = build_review_parts(make_context(str(current_photo_path)))

        self.assertIn(SYSTEM_PROMPT, parts[0]["text"])
        self.assertIn(RESPONSE_FORMAT_INSTRUCTION, parts[0]["text"])
        self.assertEqual(parts[1]["text"], "Фото рослини — 28 серпня 2026 (порівнювати поки нема з чим):")
        self.assertEqual(parts[2], {"inline_data": {"mime_type": "image/jpeg", "data": "AAEC"}})
        self.assertIn("Рослина: Кактус", parts[3]["text"])

    def test_build_review_parts_inlines_both_photos_when_a_previous_one_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            previous_photo_path = Path(directory) / "previous.jpg"
            current_photo_path = Path(directory) / "current.jpg"
            previous_photo_path.write_bytes(b"\x00")
            current_photo_path.write_bytes(b"\x01")

            parts = build_review_parts(
                make_context(
                    str(current_photo_path), previous_photo_path=str(previous_photo_path), days_since_previous_photo=5
                )
            )

        # the date, not only the gap: without it the model cannot tell november dormancy from a may problem
        self.assertEqual(parts[1]["text"], "Попереднє фото — 13 липня 2026:")
        self.assertEqual(parts[2], {"inline_data": {"mime_type": "image/jpeg", "data": "AA=="}})
        self.assertEqual(parts[3]["text"], "Нове фото — 28 серпня 2026, через 5 дн.:")
        self.assertEqual(parts[4], {"inline_data": {"mime_type": "image/jpeg", "data": "AQ=="}})
