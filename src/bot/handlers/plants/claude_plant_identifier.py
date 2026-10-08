import base64
import json
import logging

from pydantic import ValidationError

from src.bot.handlers.plants.plant_identification_prompt import SYSTEM_PROMPT
from src.infrastructure.adapters.claude_client import ClaudeClient, text_of
from src.modules.model_budget.services.usage_ledger import BudgetSpent
from src.modules.plant_care.domain import PlantIdentification

logger = logging.getLogger(__name__)

MAX_TOKENS = 1000
# identification, not invention
TEMPERATURE = 0.1
IDENTIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "common_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "species": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "watering_interval_days": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
    },
    "required": ["common_name", "species", "watering_interval_days"],
    "additionalProperties": False,
}


class ClaudePlantIdentifier:
    """
    Names an unfamiliar plant from one photo — the same contract as the gemini one.

    it sits beside the photo analyst rather than in adapters because the two share this layer's habit of
    keeping their ukrainian prompts next to the labels the family reads.
    """

    def __init__(self, client: ClaudeClient, model: str, effort: str):
        self.client = client
        self.model = model
        self.effort = effort

    async def identify(self, photo: bytes) -> PlantIdentification | None:
        content = [
            {"type": "text", "text": SYSTEM_PROMPT},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(photo).decode(),
                },
            },
        ]
        try:
            response = await self.client.complete(
                purpose="Plant identification",
                model=self.model,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                messages=[{"role": "user", "content": content}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": IDENTIFICATION_SCHEMA},
                },
            )
        except BudgetSpent:
            logger.warning("Plant identification refused: the model budget is spent")
            return None
        if response is None:
            return None
        return parse_identification(text_of(response))


def parse_identification(text: str | None) -> PlantIdentification | None:
    if text is None:
        logger.warning("Plant identification came back with no text at all")
        return None
    try:
        identification = PlantIdentification(**json.loads(text))
    except (json.JSONDecodeError, TypeError, ValidationError):
        logger.exception("Plant identification returned unparsable json: %r", text)
        return None

    # a reply that names nothing is the same as no reply, and pretending otherwise puts an empty card on screen
    if identification.common_name is None and identification.species is None:
        return None
    return identification
