import base64
import json
import logging
from typing import Any

from pydantic import ValidationError

from src.bot.handlers.plants.plant_identification_prompt import SYSTEM_PROMPT
from src.infrastructure.adapters.gemini_client import GeminiQuotaRefused, generate_content
from src.modules.plant_care.domain import PlantIdentification

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 60
# a person is waiting on the answer in the add-plant flow, so the retries are quick
RETRY_DELAYS_SECONDS = (2, 6)


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
            payload = await generate_content(
                api_key=self.api_key,
                model=self.model,
                body=body,
                purpose="Plant identification",
                timeout_seconds=REQUEST_TIMEOUT_SECONDS,
                retry_delays_seconds=RETRY_DELAYS_SECONDS,
            )
        except GeminiQuotaRefused:
            logger.warning("Plant identification refused: the gemini quota is spent")
            return None
        if payload is None:
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
