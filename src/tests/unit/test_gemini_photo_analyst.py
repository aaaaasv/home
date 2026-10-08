import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.bot.handlers.plants import gemini_photo_analyst
from src.bot.handlers.plants.gemini_photo_analyst import (
    RESPONSE_FORMAT_INSTRUCTION,
    GeminiPhotoAnalyst,
    build_review_parts,
    parse_review,
)
from src.bot.handlers.plants.photo_review_prompt import SYSTEM_PROMPT, describe_plant
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


class ReviewRequestShapeTestCase(unittest.IsolatedAsyncioTestCase):
    """What the analyst actually asks google for, which no test looked at before."""

    async def ask(self) -> dict:
        sent = {}

        async def record(**arguments):
            sent.update(arguments)
            return None

        with tempfile.TemporaryDirectory() as directory:
            current_photo_path = Path(directory) / "current.jpg"
            current_photo_path.write_bytes(b"\x00")
            with patch.object(gemini_photo_analyst, "generate_content", record):
                await GeminiPhotoAnalyst(api_key="test-key", model="gemini-test").review_photo(
                    make_context(str(current_photo_path))
                )
        return sent

    async def test_review_photo_asks_for_json_and_for_no_thinking_at_all(self):
        """942 thinking tokens against 77 of answer, and a heavier request is the one a busy free tier refuses."""
        sent = await self.ask()

        self.assertEqual(
            sent["body"]["generationConfig"],
            {"temperature": 0.2, "responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}},
        )

    async def test_review_photo_waits_minutes_rather_than_seconds_between_attempts(self):
        sent = await self.ask()

        self.assertEqual(sent["retry_delays_seconds"], (60.0, 240.0))


class DescribePlantTestCase(unittest.TestCase):
    """What the model is told about the household's own protocol for this plant."""

    def context_with(self, instructions: str | None) -> PlantPhotoReviewContext:
        context = make_context("current.jpg")
        return context.model_copy(
            update={
                "schedules": [
                    PhotoReviewSchedule(
                        task_type=CareTaskType.FERTILIZING,
                        interval_days=30,
                        days_since_last_performed=48,
                        instructions=instructions,
                    )
                ]
            }
        )

    def test_describe_plant_spells_out_the_protocol_so_the_action_can_name_the_dose(self):
        described = describe_plant(self.context_with("0.5 мл STIMUL на 1 л води"))

        self.assertIn("— добриво — раз на 30 дн., востаннє 48 дн. тому; як саме: 0.5 мл STIMUL на 1 л води", described)

    def test_describe_plant_for_a_task_with_no_protocol_leaves_the_line_as_it_was(self):
        described = describe_plant(self.context_with(None))

        self.assertIn("— добриво — раз на 30 дн., востаннє 48 дн. тому", described)
        self.assertNotIn("як саме", described)


class ReviewPromptRulesTestCase(unittest.TestCase):
    def test_the_prompt_forbids_pointing_at_the_schedule_instead_of_naming_the_number(self):
        self.assertIn("Ніколи не відсилай до графіка чи до інструкції", SYSTEM_PROMPT)

    def test_the_prompt_asks_for_the_singular_imperative_the_rest_of_the_bot_speaks(self):
        self.assertIn("Звертайся на «ти» в однині й у наказовому способі", SYSTEM_PROMPT)
