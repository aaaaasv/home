import json
import logging
from typing import Any

from pydantic import ValidationError

from src.bot.handlers.plants.photo_review_prompt import SYSTEM_PROMPT, describe_plant, format_day
from src.infrastructure.adapters.gemini_client import GeminiQuotaRefused, generate_content
from src.infrastructure.adapters.image_encoding import read_image_base64
from src.modules.plant_care.domain import PlantPhotoReview, PlantPhotoReviewContext

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 60

# gemini honours responseMimeType=application/json, but not a fixed shape — so the keys are spelled out here and
# the result is validated on parse rather than trusted
RESPONSE_FORMAT_INSTRUCTION = (
    "Поверни лише JSON-обʼєкт з полями status, summary, change, action. "
    'status — одне з: "ok", "watch", "problem". change та action — рядок або null.'
)


class GeminiPhotoAnalyst:
    """The plant photo reviewer on google's free-tier gemini — the same PhotoAnalyst contract as the anthropic one"""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def review_photo(self, context: PlantPhotoReviewContext) -> PlantPhotoReview | None:
        try:
            parts = build_review_parts(context)
        except OSError:
            logger.exception("Could not read the stored photos of '%s'", context.plant_name)
            return None

        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }
        try:
            payload = await generate_content(
                api_key=self.api_key,
                model=self.model,
                body=body,
                purpose=f"Photo review for '{context.plant_name}'",
                timeout_seconds=REQUEST_TIMEOUT_SECONDS,
            )
        except GeminiQuotaRefused:
            logger.warning("Photo review for '%s' refused: the gemini quota is spent", context.plant_name)
            return None
        if payload is None:
            return None
        return parse_review(payload, context.plant_name)


def build_review_parts(context: PlantPhotoReviewContext) -> list[dict[str, Any]]:
    """The one multimodal turn: the instruction, then both photos with their labels and the plant data."""
    parts: list[dict[str, Any]] = [{"text": f"{SYSTEM_PROMPT}\n\n{RESPONSE_FORMAT_INSTRUCTION}"}]
    if context.previous_photo_path is not None:
        # the date, not only the gap: the same yellowing leaf reads as dormancy in november and as trouble in may
        parts.append({"text": f"Попереднє фото — {format_day(context.previous_photo_taken_on)}:"})
        parts.append(_image_part(context.previous_photo_path))
        parts.append(
            {
                "text": f"Нове фото — {format_day(context.current_photo_taken_on)}, "
                f"через {context.days_since_previous_photo} дн.:"
            }
        )
    else:
        parts.append(
            {"text": f"Фото рослини — {format_day(context.current_photo_taken_on)} (порівнювати поки нема з чим):"}
        )
    parts.append(_image_part(context.current_photo_path))
    parts.append({"text": describe_plant(context)})
    return parts


def _image_part(path: str) -> dict[str, Any]:
    return {"inline_data": {"mime_type": "image/jpeg", "data": read_image_base64(path)}}


def parse_review(payload: dict[str, Any], plant_name: str) -> PlantPhotoReview | None:
    """The review json at candidates[0].content.parts[*].text — None on anything that will not validate"""
    candidates = payload.get("candidates")
    if not candidates:
        logger.warning("Photo review of '%s' returned no candidates", plant_name)
        return None
    parts = candidates[0].get("content", {}).get("parts")
    if not parts:
        logger.warning("Photo review of '%s' returned no content", plant_name)
        return None

    text = "".join(part.get("text", "") for part in parts)
    try:
        return PlantPhotoReview(**json.loads(text))
    except (json.JSONDecodeError, TypeError, ValidationError):
        logger.exception("Photo review of '%s' returned unparsable json: %r", plant_name, text)
        return None
