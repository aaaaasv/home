"""The assistant on anthropic — a thin adapter behind LanguageModel, the sibling of the gemini one."""

import base64
import logging
from collections.abc import Sequence
from typing import Any, Protocol

from src.infrastructure.adapters.claude_client import ClaudeClient, text_of
from src.modules.assistant.services.language_model import MODEL_ROLE, ConversationTurn, QuotaExhausted
from src.modules.model_budget.services.usage_ledger import BudgetSpent

logger = logging.getLogger(__name__)


class HouseholdToolbox(Protocol):
    """What the assistant may look things up with — a protocol, so the adapter stays an adapter."""

    @property
    def definitions(self) -> list[dict[str, Any]]:
        ...

    async def run(self, name: str, arguments: dict[str, Any]) -> str:
        ...


MAX_TOKENS = 2000
# somebody is watching the chat for this answer, so the model gets a few searches and not a research project
MAX_SEARCHES_PER_ANSWER = 3
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES_PER_ANSWER}
# the conversation is kept in gemini's words, where the model's own turn is "model"; anthropic calls it
# "assistant", and the memory outlives a provider swap
ANTHROPIC_ROLES = {MODEL_ROLE: "assistant"}


class ClaudeLanguageModel:
    """
    Answers a conversation, grounding it in a web search when the question reaches past the household facts.

    the endpoint keeps no session, so the whole conversation is resent every time — the same shape the gemini
    adapter worked in, which is why swapping providers is this class and nothing else.
    """

    def __init__(
        self,
        client: ClaudeClient,
        model: str,
        effort: str,
        tools: HouseholdToolbox | None = None,
    ):
        self.client = client
        self.model = model
        self.effort = effort
        self.tools = tools

    async def generate(self, conversation: Sequence[ConversationTurn], system_instruction: str) -> str | None:
        request = {
            "max_tokens": MAX_TOKENS,
            "system": system_instruction,
            "output_config": {"effort": self.effort},
        }
        messages = [build_turn(turn) for turn in conversation]
        try:
            if self.tools is None:
                response = await self.client.complete(
                    purpose="Assistant answer",
                    model=self.model,
                    messages=messages,
                    tools=[WEB_SEARCH_TOOL],
                    **request,
                )
            else:
                response = await self.client.complete_with_tools(
                    purpose="Assistant answer",
                    model=self.model,
                    tools=[*self.tools.definitions, WEB_SEARCH_TOOL],
                    run_tool=self.tools.run,
                    messages=messages,
                    **request,
                )
        except BudgetSpent as refusal:
            # the family is told about an allowance in the words it already has for a spent quota
            raise QuotaExhausted(is_daily=refusal.is_daily) from None
        if response is None:
            return None
        return text_of(response)


def build_turn(turn: ConversationTurn) -> dict[str, Any]:
    """One turn — its text plus any images inlined as base64."""
    content: list[dict[str, Any]] = [{"type": "text", "text": turn.text}]
    for image in turn.images:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image.mime_type,
                    "data": base64.standard_b64encode(image.data).decode("utf-8"),
                },
            }
        )
    return {"role": ANTHROPIC_ROLES.get(turn.role, turn.role), "content": content}
