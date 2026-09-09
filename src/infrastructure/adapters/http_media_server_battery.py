import logging
from datetime import datetime, timedelta

import aiohttp

from src.common.time import current_time
from src.modules.power.domain import MediaServerState

logger = logging.getLogger(__name__)


class HttpMediaServerBattery:
    """
    Reads the media server's battery over http, from the small agent that runs on the box itself.

    an endpoint rather than ssh or mqtt, for the same reason `pi-health` is one: the bot's container holds no
    keys to any other machine, and opening the broker to the lan would widen what a compromised device on the
    wi-fi can reach for the sake of four numbers. the box already serves http; this is one more path on it.

    it reads whether the socket feeding that box is live, which during a blackout is the same socket the pi is
    on — but this reading arrives over the lan, so it is worth nothing when the router is the thing that died.
    that is why mains detection stays on the hat and this only fills a row.
    """

    def __init__(self, url: str, timeout_seconds: float, stale_after: timedelta):
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.stale_after = stale_after

    async def read_state(self) -> MediaServerState | None:
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.url) as response:
                    response.raise_for_status()
                    published = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as error:
            # the box is asleep, halted for the blackout, or off the network — all of which the row says as one
            logger.info("Media server battery did not answer: %s", error)
            return None
        except ValueError as error:
            # a truncated body, or something on the lan answering on that port that is not the agent
            logger.warning("Media server battery answered with something that is not a reading: %s", error)
            return None

        state = self._parse(published)
        if state is None:
            return None
        # the agent stamps every response, so a proxy or a frozen box serving a cached body cannot pass for live
        if current_time() - state.as_of > self.stale_after:
            logger.warning("Media server battery reading is stale — published at %s", state.as_of)
            return None
        return state

    def _parse(self, published: dict) -> MediaServerState | None:
        try:
            return MediaServerState(
                on_mains=published["on_mains"],
                is_charging=published["is_charging"],
                charge_percent=published["charge_percent"],
                energy_watt_hours=published["energy_watt_hours"],
                power_watts=published["power_watts"],
                as_of=datetime.fromisoformat(published["as_of"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            logger.warning("Media server battery response does not hold a reading: %s", error)
            return None
