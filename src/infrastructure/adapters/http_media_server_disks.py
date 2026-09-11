import logging

import aiohttp

from src.modules.system_health.domain import DiskReading

logger = logging.getLogger(__name__)


class HttpMediaServerDisks:
    """
    Reads SMART from the media server over the same http agent that already serves its battery.

    the probe behind this endpoint runs as root on that machine and writes a file; the agent only passes it
    on. that split is why nothing privileged listens on a socket there, and why this side needs no keys.
    """

    def __init__(self, url: str, timeout_seconds: float):
        self.url = url
        self.timeout_seconds = timeout_seconds

    async def read(self) -> list[DiskReading] | None:
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.url) as response:
                    response.raise_for_status()
                    published = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as error:
            # halted for a blackout, asleep, or off the network — none of which is a disk fault
            logger.info("Media server disks did not answer: %s", error)
            return None
        except ValueError as error:
            logger.warning("Media server disks answered with something that is not a report: %s", error)
            return None

        return self._parse(published)

    def _parse(self, published: dict) -> list[DiskReading] | None:
        try:
            return [DiskReading(**disk) for disk in published["disks"]]
        except (KeyError, TypeError, ValueError) as error:
            logger.warning("Media server disk report does not hold readings: %s", error)
            return None
