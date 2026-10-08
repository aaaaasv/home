import json
import logging

from pydantic import ValidationError

from src.bot.handlers.plants.photo_review_prompt import SYSTEM_PROMPT, describe_plant, format_day
from src.common.constants import PlantPhotoReviewStatus
from src.infrastructure.adapters.claude_client import ClaudeClient, text_of
from src.infrastructure.adapters.image_encoding import read_image_base64
from src.modules.model_budget.services.usage_ledger import BudgetSpent
from src.modules.plant_care.domain import PlantPhotoReview, PlantPhotoReviewContext

logger = logging.getLogger(__name__)

MAX_TOKENS = 8000

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
    """The plant photo reviewer on anthropic — the same PhotoAnalyst contract as the gemini one."""

    def __init__(self, client: ClaudeClient, model: str):
        self.client = client
        self.model = model

    async def review_photo(self, context: PlantPhotoReviewContext) -> PlantPhotoReview | None:
        try:
            content = build_review_content(context)
        except OSError:
            logger.exception("Could not read the stored photos of '%s'", context.plant_name)
            return None

        purpose = f"Photo review for '{context.plant_name}'"
        try:
            response = await self.client.complete(
                purpose=purpose,
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_config={"format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
            )
        except BudgetSpent:
            logger.warning("%s refused: the model budget is spent", purpose)
            return None
        if response is None:
            return None

        return parse_review(text_of(response), context.plant_name)


def parse_review(text: str | None, plant_name: str) -> PlantPhotoReview | None:
    if text is None:
        logger.warning("Photo review of '%s' came back with no text at all", plant_name)
        return None
    try:
        return PlantPhotoReview(**json.loads(text))
    except (json.JSONDecodeError, TypeError, ValidationError):
        logger.exception("Photo review of '%s' returned unparsable json: %r", plant_name, text)
        return None


def build_review_content(context: PlantPhotoReviewContext) -> list[dict]:
    """The one multimodal turn: the instruction, then both photos with their dates and the plant's record."""
    content: list[dict] = []
    if context.previous_photo_path is not None:
        # the date, not only the gap: the same yellowing leaf reads as dormancy in november and as trouble in may
        content.append({"type": "text", "text": f"Попереднє фото — {format_day(context.previous_photo_taken_on)}:"})
        content.append(_build_image(context.previous_photo_path))
        content.append(
            {
                "type": "text",
                "text": f"Нове фото — {format_day(context.current_photo_taken_on)}, "
                f"через {context.days_since_previous_photo} дн.:",
            }
        )
    else:
        content.append(
            {
                "type": "text",
                "text": f"Фото рослини — {format_day(context.current_photo_taken_on)} "
                "(порівнювати поки нема з чим):",
            }
        )
    content.append(_build_image(context.current_photo_path))
    content.append({"type": "text", "text": describe_plant(context)})
    return content


def _build_image(path: str) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": read_image_base64(path)},
    }
