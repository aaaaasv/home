import asyncio
import base64
import json
import logging
from typing import Any

import aiohttp
from pydantic import ValidationError

from src.bot.handlers.plants.plant_identification_prompt import SYSTEM_PROMPT
from src.modules.plant_care.domain import PlantIdentification

logger = logging.getLogger(__name__)

GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REQUEST_TIMEOUT_SECONDS = 60


class GeminiPlantIdentifier:
    """
    Names an unfamiliar plant from one photo on google's free-tier gemini.

    it sits beside the photo analyst rather than in adapters because the two share this layer's habit of
    keeping their ukrainian prompts next to the labels the family reads.
    """

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def identify(self, photo: bytes) -> PlantIdentification | None:
        url = GENERATE_CONTENT_URL.format(model=self.model)
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": SYSTEM_PROMPT},
                        {"inline_data": {"mime_type": "image/jpeg", "data": base64.standard_b64encode(photo).decode()}},
                    ]
                }
            ],
            # a low temperature because this is identification, not invention
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
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
                "Plant identification failed: %s (HTTP %s)", type(error).__name__, getattr(error, "status", "?")
            )
            return None

        return parse_identification(payload)


def parse_identification(payload: dict[str, Any]) -> PlantIdentification | None:
    """The json at candidates[0].content.parts[*].text — None on anything that will not validate"""
    candidates = payload.get("candidates")
    if not candidates:
        logger.warning("Plant identification returned no candidates")
        return None
    parts = candidates[0].get("content", {}).get("parts")
    if not parts:
        logger.warning("Plant identification returned no content")
        return None

    text = "".join(part.get("text", "") for part in parts)
    try:
        identification = PlantIdentification(**json.loads(text))
    except (json.JSONDecodeError, TypeError, ValidationError):
        logger.exception("Plant identification returned unparsable json: %r", text)
        return None

    # a reply that names nothing is the same as no reply, and pretending otherwise puts an empty card on screen
    if identification.common_name is None and identification.species is None:
        return None
    return identification
