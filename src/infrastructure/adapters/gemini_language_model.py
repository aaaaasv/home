import base64
import logging
from collections.abc import Sequence
from typing import Any

from src.infrastructure.adapters.gemini_client import GeminiQuotaRefused, generate_content
from src.modules.assistant.services.language_model import ConversationTurn, QuotaExhausted

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30
# someone asked in the chat and is watching for the answer, so the retries are quick
RETRY_DELAYS_SECONDS = (2, 6)


class GeminiLanguageModel:
    """
    Google's free-tier gemini via the stateless generateContent endpoint — a thin adapter behind LanguageModel,
    so swapping to a paid model or a local one is a new class here and nothing else. the endpoint keeps no session,
    so the whole conversation is resent every time. it grounds answers in a google search when the question needs
    facts beyond the prompt, and it reads images. returns None on any failure
    """

    def __init__(self, api_key: str, model: str, temperature: float = 0.2):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature

    async def generate(self, conversation: Sequence[ConversationTurn], system_instruction: str) -> str | None:
        body = build_request_body(conversation, system_instruction, self.temperature)
        try:
            payload = await generate_content(
                api_key=self.api_key,
                model=self.model,
                body=body,
                purpose="Assistant answer",
                timeout_seconds=REQUEST_TIMEOUT_SECONDS,
                retry_delays_seconds=RETRY_DELAYS_SECONDS,
            )
        except GeminiQuotaRefused as refusal:
            raise QuotaExhausted(is_daily=names_the_daily_quota(refusal.body)) from None
        if payload is None:
            return None
        return extract_answer_text(payload)


def names_the_daily_quota(error_body: str) -> bool:
    """
    A 429 spells out the quota it hit — GenerateRequestsPerDayPerProjectPerModel-FreeTier for a spent day. an
    unrecognised body counts as the minute limit: asking again in a minute costs the family nothing
    """
    return "PerDay" in error_body


def build_request_body(
    conversation: Sequence[ConversationTurn], system_instruction: str, temperature: float
) -> dict[str, Any]:
    """One generateContent body — the conversation as gemini turns, the grounding as a system instruction"""
    return {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [build_content_turn(turn) for turn in conversation],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": temperature},
    }


def build_content_turn(turn: ConversationTurn) -> dict[str, Any]:
    """One turn — its text plus any images inlined as base64"""
    parts: list[dict[str, Any]] = [{"text": turn.text}]
    for image in turn.images:
        encoded = base64.standard_b64encode(image.data).decode("utf-8")
        parts.append({"inline_data": {"mime_type": image.mime_type, "data": encoded}})
    return {"role": turn.role, "parts": parts}


def extract_answer_text(payload: dict[str, Any]) -> str | None:
    """The answer text joined from candidates[0].content.parts[*].text — the stable generateContent shape"""
    candidates = payload.get("candidates")
    if not candidates:
        return None
    parts = candidates[0].get("content", {}).get("parts")
    if not parts:
        return None
    text = "".join(part.get("text", "") for part in parts).strip()
    return text or None
