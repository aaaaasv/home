"""
One generateContent call to google's gemini, retried past the moments the model is overloaded.

on the free tier a 503 «the model is overloaded» is an everyday answer that clears within seconds to a minute, so
giving up on the first one silently lost a plant's photo review. a quota refusal does not clear by asking again,
so a 429 is handed back to the caller at once instead.
"""

import asyncio
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TOO_MANY_REQUESTS = 429
BAD_REQUEST = 400
OVERLOADED_STATUSES = frozenset({500, 502, 503, 504})
# the waits grow so the last attempt lands well clear of the spike that refused the first
DEFAULT_RETRY_DELAYS_SECONDS = (5, 20)
# enough of google's answer to name the trouble, short enough not to fill the journal with one refusal
LOGGED_BODY_LIMIT = 300


class GeminiQuotaRefused(Exception):
    """Gemini said 429; the body names which quota ran out."""

    def __init__(self, body: str):
        super().__init__("Gemini quota refused")
        self.body = body


class GeminiRefused(Exception):
    """Any other refusal, carrying what google actually said rather than only the number it said it with."""

    def __init__(self, status: int, body: str):
        super().__init__(f"Gemini refused with HTTP {status}")
        self.status = status
        self.body = body


def _shorten(body: str) -> str:
    collapsed = " ".join(body.split())
    return collapsed if len(collapsed) <= LOGGED_BODY_LIMIT else f"{collapsed[:LOGGED_BODY_LIMIT]}…"


async def generate_content(
    api_key: str,
    model: str,
    body: dict[str, Any],
    purpose: str,
    timeout_seconds: float,
    retry_delays_seconds: tuple[float, ...] = DEFAULT_RETRY_DELAYS_SECONDS,
    url_template: str = GENERATE_CONTENT_URL,
) -> dict[str, Any] | None:
    """The response payload, or None once every attempt failed; raises GeminiQuotaRefused on a 429."""
    url = url_template.format(model=model)
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    attempts = len(retry_delays_seconds) + 1
    for attempt in range(1, attempts + 1):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as session:
                async with session.post(url, headers=headers, json=body) as response:
                    if response.status == TOO_MANY_REQUESTS:
                        raise GeminiQuotaRefused(await response.text())
                    if response.status >= BAD_REQUEST:
                        raise GeminiRefused(response.status, _shorten(await response.text()))
                    return await response.json()
        except GeminiRefused as refusal:
            # never the error object in a log line: its repr carries the request headers, the api key among them
            if refusal.status not in OVERLOADED_STATUSES:
                logger.warning("%s failed: HTTP %s — %s", purpose, refusal.status, refusal.body)
                return None
            # the body is what names the actual trouble; the status alone sent me measuring the key, the model
            # and the network for an hour over a plain "the model is overloaded"
            failure = f"HTTP {refusal.status} — {refusal.body}"
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            failure = type(error).__name__

        if attempt == attempts:
            logger.warning("%s failed after %d attempts: %s", purpose, attempts, failure)
            return None
        delay = retry_delays_seconds[attempt - 1]
        logger.info("%s attempt %d of %d failed (%s), retrying in %ss", purpose, attempt, attempts, failure, delay)
        await asyncio.sleep(delay)
    return None
