import asyncio
import json
import logging
from typing import Any

import aiohttp
from pydantic import TypeAdapter, ValidationError

from src.modules.newspaper.domain import CrosswordClue, normalize_answer

logger = logging.getLogger(__name__)

GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REQUEST_TIMEOUT_SECONDS = 90
REQUESTED_WORDS = 40
# the prompt names recent answers so they are not offered again; past this many the request only grows
EXCLUDED_WORDS_IN_PROMPT = 300

PROMPT = """Склади {count} слів для українського кросворду середньої складності — для дорослого, який любить \
розгадувати кросворди в газеті.

Вимоги до слова:
- український іменник у називному відмінку, одне слово, лише літери (без апострофа, дефіса, пробілу)
- від 5 до 12 літер
- загальновідоме, але не дитяче: географія, природа, наука, історія, мистецтво, література, музика, спорт, \
побут, ремесла
- жодних слів, пов'язаних з війною, політикою сьогодення чи чиїмось приватним життям

Вимоги до питання:
- до 70 символів, без самого слова і без спільного з ним кореня
- лише перевірені, загальновизнані факти; якщо сумніваєшся у факті — візьми інше слово
- не «синонім до …», а коротке точне означення або факт, за яким слово вгадується однозначно

Не пропонуй жодного з цих слів: {excluded}

Поверни лише JSON-масив об'єктів з полями answer і clue."""


class GeminiWordSource:
    """
    Fresh words for the week from google's free-tier gemini, so the grid is not always drawn from the same list.

    nobody reads these clues before they are printed, which is why the checked word bank still stands behind
    it: whatever gemini offers is filtered by the same rules as the bank, and on any failure the week is built
    from the bank alone.
    """

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def fetch_clues(self, excluded_answers: set[str]) -> list[CrosswordClue]:
        url = GENERATE_CONTENT_URL.format(model=self.model)
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        excluded = ", ".join(sorted(excluded_answers)[:EXCLUDED_WORDS_IN_PROMPT]) or "—"
        body = {
            "contents": [{"parts": [{"text": PROMPT.format(count=REQUESTED_WORDS, excluded=excluded)}]}],
            "generationConfig": {"temperature": 0.9, "responseMimeType": "application/json"},
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
                "Crossword words from Gemini failed: %s (HTTP %s)", type(error).__name__, getattr(error, "status", "?")
            )
            return []
        return parse_clues(payload)


def parse_clues(payload: dict[str, Any]) -> list[CrosswordClue]:
    """The json array at candidates[0].content.parts[*].text — an empty list on anything that will not validate."""
    candidates = payload.get("candidates")
    parts = candidates[0].get("content", {}).get("parts") if candidates else None
    if not parts:
        logger.warning("Crossword words from Gemini came back empty")
        return []

    text = "".join(part.get("text", "") for part in parts)
    try:
        offered = TypeAdapter(list[CrosswordClue]).validate_python(json.loads(text))
    except (json.JSONDecodeError, ValidationError):
        logger.warning("Crossword words from Gemini were not the expected json: %r", text[:500])
        return []
    return [CrosswordClue(answer=normalize_answer(clue.answer), clue=clue.clue.strip()) for clue in offered]
