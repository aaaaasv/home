"""
Every paid call to Anthropic goes through here, so the money is counted in exactly one place.

the free tier used to be the spending guard by accident: it refused after twenty requests a day and the worst
a runaway job could do was go quiet. a key with credit behind it has no such floor, so the ledger is asked
before the call and told after it — and a call that was never made is never billed.
"""

import logging
from typing import Any

from anthropic import APIError, AsyncAnthropic
from anthropic.types import Message

from src.modules.model_budget.services.usage_ledger import UsageLedger

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 120.0
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
        if response.stop_reason != "end_turn":
            logger.warning("%s stopped with '%s'", purpose, response.stop_reason)
            return None
        return response


def text_of(response: Message) -> str | None:
    """The answer's text blocks joined — a response made only of tool calls or thinking has none."""
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return text or None
