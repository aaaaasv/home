import asyncio
import json
import logging
from typing import Any

import aiohttp
from pydantic import ValidationError

from src.bot.handlers.plants.photo_review_prompt import SYSTEM_PROMPT, describe_plant
from src.infrastructure.adapters.image_encoding import read_image_base64
from src.modules.plant_care.domain import PlantPhotoReview, PlantPhotoReviewContext

logger = logging.getLogger(__name__)

GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
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

        url = GENERATE_CONTENT_URL.format(model=self.model)
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=body) as response:
                    response.raise_for_status()
                    payload = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            # never logger.exception here: the aiohttp error repr carries the request headers, incl. the api key
            logger.warning(
                "Photo review failed for '%s': %s (HTTP %s)",
                context.plant_name,
                type(error).__name__,
                getattr(error, "status", "?"),
            )
            return None

        return parse_review(payload, context.plant_name)


def build_review_parts(context: PlantPhotoReviewContext) -> list[dict[str, Any]]:
    """The one multimodal turn: the instruction, then both photos with their labels and the plant data."""
    parts: list[dict[str, Any]] = [{"text": f"{SYSTEM_PROMPT}\n\n{RESPONSE_FORMAT_INSTRUCTION}"}]
    if context.previous_photo_path is not None:
        parts.append({"text": f"Попереднє фото ({context.days_since_previous_photo} дн. тому):"})
        parts.append(_image_part(context.previous_photo_path))
        parts.append({"text": "Нове фото (щойно):"})
    else:
        parts.append({"text": "Фото рослини (порівнювати поки нема з чим):"})
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
