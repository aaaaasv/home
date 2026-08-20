import json
import logging

from anthropic import APIError, AsyncAnthropic
from anthropic.types import Message

from src.bot.handlers.plants.photo_review_prompt import SYSTEM_PROMPT, describe_plant
from src.common.constants import PlantPhotoReviewStatus
from src.infrastructure.adapters.image_encoding import read_image_base64
from src.modules.plant_care.domain import PlantPhotoReview, PlantPhotoReviewContext

logger = logging.getLogger(__name__)

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": [status.value for status in PlantPhotoReviewStatus]},
        "summary": {"type": "string"},
        "change": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "action": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["status", "summary", "change", "action"],
    "additionalProperties": False,
}


class ClaudePhotoAnalyst:
    def __init__(self, api_key: str, model: str):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def review_photo(self, context: PlantPhotoReviewContext) -> PlantPhotoReview | None:
        try:
            content = self._build_content(context)
        except OSError:
            logger.exception("Could not read the stored photos of '%s'", context.plant_name)
            return None

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                thinking={"type": "adaptive"},
                output_config={"effort": "high", "format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
            )
        except APIError:
            logger.exception("Photo review failed for '%s'", context.plant_name)
            return None

        return self._parse(response, context.plant_name)

    def _parse(self, response: Message, plant_name: str) -> PlantPhotoReview | None:
        # anything but a clean finish (a refusal, or json cut off by max_tokens) leaves nothing safe to parse
        if response.stop_reason != "end_turn":
            logger.warning("Photo review of '%s' stopped with '%s'", plant_name, response.stop_reason)
            return None

        text = next(block.text for block in response.content if block.type == "text")
        return PlantPhotoReview(**json.loads(text))

    def _build_content(self, context: PlantPhotoReviewContext) -> list[dict]:
        content: list[dict] = []
        if context.previous_photo_path is not None:
            content.append({"type": "text", "text": f"Попереднє фото ({context.days_since_previous_photo} дн. тому):"})
            content.append(self._build_image(context.previous_photo_path))
            content.append({"type": "text", "text": "Нове фото (щойно):"})
        else:
            content.append({"type": "text", "text": "Фото рослини (порівнювати поки нема з чим):"})
        content.append(self._build_image(context.current_photo_path))
        content.append({"type": "text", "text": describe_plant(context)})
        return content

    def _build_image(self, path: str) -> dict:
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": read_image_base64(path)},
        }
