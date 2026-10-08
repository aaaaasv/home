import json
import logging

from pydantic import TypeAdapter, ValidationError

from src.bot.handlers.newspaper.gemini_word_source import EXCLUDED_WORDS_IN_PROMPT, PROMPT, REQUESTED_WORDS
from src.infrastructure.adapters.claude_client import ClaudeClient, text_of
from src.modules.model_budget.services.usage_ledger import BudgetSpent
from src.modules.newspaper.domain import CrosswordClue, normalize_answer

logger = logging.getLogger(__name__)

MAX_TOKENS = 4000
# forty words that should not resemble each other, so the model is given room to wander
TEMPERATURE = 0.9
CLUES_SCHEMA = {
    "type": "object",
    "properties": {
        "clues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"answer": {"type": "string"}, "clue": {"type": "string"}},
                "required": ["answer", "clue"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clues"],
    "additionalProperties": False,
}


class ClaudeWordSource:
    """
    Fresh words for the week, so the grid is not always drawn from the same list.

    nobody reads these clues before they are printed, which is why the checked word bank still stands behind
    it: whatever comes back is filtered by the same rules as the bank, and on any failure the week is built
    from the bank alone. the prompt is shared with the gemini source — the words wanted do not depend on who
    is asked for them.
    """

    def __init__(self, client: ClaudeClient, model: str):
        self.client = client
        self.model = model

    async def fetch_clues(self, excluded_answers: set[str]) -> list[CrosswordClue]:
        excluded = ", ".join(sorted(excluded_answers)[:EXCLUDED_WORDS_IN_PROMPT]) or "—"
        try:
            response = await self.client.complete(
                purpose="Crossword words",
                model=self.model,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                messages=[{"role": "user", "content": PROMPT.format(count=REQUESTED_WORDS, excluded=excluded)}],
                output_config={"format": {"type": "json_schema", "schema": CLUES_SCHEMA}},
            )
        except BudgetSpent:
            logger.warning("Crossword words refused: the model budget is spent, the bank covers this week")
            return []
        if response is None:
            return []
        return parse_clues(text_of(response))


def parse_clues(text: str | None) -> list[CrosswordClue]:
    """An empty list on anything that will not validate — the bank is behind this and the paper still prints."""
    if text is None:
        logger.warning("Crossword words came back with no text at all")
        return []
    try:
        offered = TypeAdapter(list[CrosswordClue]).validate_python(json.loads(text)["clues"])
    except (json.JSONDecodeError, KeyError, TypeError, ValidationError):
        logger.warning("Crossword words were not the expected json: %r", text[:500])
        return []
    # a clue is printed as a line in a list, and a full stop at the end of one reads like a typo there
    return [CrosswordClue(answer=normalize_answer(clue.answer), clue=clue.clue.strip().rstrip(".")) for clue in offered]
