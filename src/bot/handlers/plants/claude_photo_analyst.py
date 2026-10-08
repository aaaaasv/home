import json
import logging
from collections.abc import Callable

from pydantic import ValidationError

from src.bot.handlers.plants.photo_review_prompt import SYSTEM_PROMPT, describe_plant, format_day
from src.bot.handlers.plants.review_tools import REVIEW_TOOLS, PlantReviewTools
from src.common.constants import PlantPhotoReviewStatus
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.adapters.claude_client import ClaudeClient, text_of
from src.infrastructure.adapters.claude_language_model import WEB_SEARCH_TOOL
from src.infrastructure.adapters.image_encoding import read_image_base64
from src.infrastructure.db.uow import UnitOfWork
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
    """
    The plant photo reviewer on anthropic — the same PhotoAnalyst contract as the gemini one.

    it is handed two frames and the plant's record, and it may go looking for the rest: earlier photos, the
    care log, the room's weather, the web. nothing it can reach says more than the herbarium sheet already
    shows the family, and most reviews never ask for any of it.
    """

    def __init__(
        self,
        client: ClaudeClient,
        model: str,
        effort: str,
        uow_factory: Callable[[], UnitOfWork] | None = None,
        household_calendar: HouseholdCalendar | None = None,
    ):
        self.client = client
        self.model = model
        self.effort = effort
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar

    async def review_photo(self, context: PlantPhotoReviewContext) -> PlantPhotoReview | None:
        try:
            content = build_review_content(context)
        except OSError:
            logger.exception("Could not read the stored photos of '%s'", context.plant_name)
            return None

        purpose = f"Photo review for '{context.plant_name}'"
        request = {
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "output_config": {"effort": self.effort, "format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
        }
        try:
            if self.uow_factory is None or self.household_calendar is None or context.plant_id is None:
                response = await self.client.complete(
                    purpose=purpose, model=self.model, messages=[{"role": "user", "content": content}], **request
                )
            else:
                tools = PlantReviewTools(
                    plant_id=context.plant_id,
                    uow_factory=self.uow_factory,
                    household_calendar=self.household_calendar,
                )
                response = await self.client.complete_with_tools(
                    purpose=purpose,
                    model=self.model,
                    tools=[*REVIEW_TOOLS, WEB_SEARCH_TOOL],
                    run_tool=tools.run,
                    messages=[{"role": "user", "content": content}],
                    **request,
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
