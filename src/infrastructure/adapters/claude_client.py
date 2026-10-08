"""
Every paid call to Anthropic goes through here, so the money is counted in exactly one place.

the free tier used to be the spending guard by accident: it refused after twenty requests a day and the worst
a runaway job could do was go quiet. a key with credit behind it has no such floor, so the ledger is asked
before the call and told after it — and a call that was never made is never billed.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from anthropic import APIError, AsyncAnthropic
from anthropic.types import Message

from src.modules.model_budget.services.usage_ledger import UsageLedger

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 120.0
# how many times the model may come back asking for more before the answer is taken as it stands. it is a
# ceiling on cost and on waiting, not a target: most reviews never use a tool at all
MAX_TOOL_ROUNDS = 6
# the sdk already backs off and retries a 429 or a 5xx; two is enough for a blip and short enough that
# somebody waiting in the chat is not left staring at «думаю» for minutes
DEFAULT_RETRIES = 2


class ClaudeClient:
    def __init__(
        self,
        api_key: str,
        ledger: UsageLedger,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
    ):
        self.client = AsyncAnthropic(api_key=api_key, timeout=timeout_seconds, max_retries=retries)
        self.ledger = ledger

    async def complete(self, purpose: str, model: str, **request: Any) -> Message | None:
        """
        The answer, or None when anthropic could not give one. Raises BudgetSpent before spending anything.

        a refusal to spend is not a failure to answer, so it is raised rather than returned: the caller has
        something different to tell the family about an allowance than about a model that did not reply.
        """
        response = await self._ask(purpose, model, **request)
        if response is None:
            return None
        if response.stop_reason != "end_turn":
            return self._stopped(purpose, response)
        return response

    async def complete_with_tools(
        self,
        purpose: str,
        model: str,
        tools: list[dict[str, Any]],
        run_tool: Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]] | str]],
        messages: list[dict[str, Any]],
        max_rounds: int = MAX_TOOL_ROUNDS,
        **request: Any,
    ) -> Message | None:
        """
        The same call, but the model may ask for things on the way to answering.

        every round is a call of its own: billed on its own, and checked against the allowance on its own, so
        a model that keeps asking runs into the budget exactly like one that keeps being asked.
        """
        conversation = list(messages)
        for _ in range(max_rounds):
            response = await self._ask(purpose, model, messages=conversation, tools=tools, **request)
            if response is None:
                return None
            if response.stop_reason != "tool_use":
                return response if response.stop_reason == "end_turn" else self._stopped(purpose, response)

            conversation.append({"role": "assistant", "content": response.content})
            conversation.append({"role": "user", "content": await self._answer_tools(response, run_tool)})

        logger.warning("%s kept asking for more past %s rounds", purpose, max_rounds)
        return None

    async def _answer_tools(self, response: Message, run_tool) -> list[dict[str, Any]]:
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                content = await run_tool(block.name, dict(block.input))
            except Exception:
                logger.exception("Tool %s failed", block.name)
                content = "Інструмент не відповів."
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
        return results

    async def _ask(self, purpose: str, model: str, **request: Any) -> Message | None:
        await self.ledger.refuse_if_spent()
        try:
            response = await self.client.messages.create(model=model, **request)
        except APIError:
            # never the error object itself: its repr carries the request headers, the api key among them
            logger.exception("%s failed", purpose)
            return None
        await self.ledger.record(
            purpose=purpose,
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        return response

    def _stopped(self, purpose: str, response: Message) -> None:
        logger.warning("%s stopped with '%s'", purpose, response.stop_reason)
        return None


def text_of(response: Message) -> str | None:
    """The answer's text blocks joined — a response made only of tool calls or thinking has none."""
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return text or None
