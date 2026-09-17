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
OVERLOADED_STATUSES = frozenset({500, 502, 503, 504})
# the waits grow so the last attempt lands well clear of the spike that refused the first
DEFAULT_RETRY_DELAYS_SECONDS = (5, 20)


class GeminiQuotaRefused(Exception):
    """Gemini said 429; the body names which quota ran out."""

    def __init__(self, body: str):
        super().__init__("Gemini quota refused")
        self.body = body


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
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientResponseError as error:
            # never the error object in a log line: its repr carries the request headers, the api key among them
            if error.status not in OVERLOADED_STATUSES:
                logger.warning("%s failed: HTTP %s", purpose, error.status)
                return None
            failure = f"HTTP {error.status}"
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            failure = type(error).__name__

        if attempt == attempts:
            logger.warning("%s failed after %d attempts: %s", purpose, attempts, failure)
            return None
        delay = retry_delays_seconds[attempt - 1]
        logger.info("%s attempt %d of %d failed (%s), retrying in %ss", purpose, attempt, attempts, failure, delay)
        await asyncio.sleep(delay)
    return None
