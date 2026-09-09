import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.common.time import current_time
from src.modules.power.domain import UpsState

logger = logging.getLogger(__name__)


class X728PiUps:
    """
    Reads the X728's state from the file the host agent publishes, rather than touching the board itself.

    the gpio line and the i2c gauge could be read from here, but the agent that watches them has to exist
    anyway: nothing in a container may halt the machine, and an unattended pi on a dying pack must halt itself
    whether or not the bot is running. once that agent exists, the bot reading its file costs nothing and buys
    a great deal — no device mounts, no gpio group, and a linux-only c extension kept out of the test suite.
    the same trade the pi-health sensor makes with sysfs.
    """

    def __init__(self, state_path: str, stale_after: timedelta):
        self.state_path = Path(state_path)
        self.stale_after = stale_after

    async def read_state(self) -> UpsState | None:
        try:
            published = json.loads(self.state_path.read_text())
        except FileNotFoundError:
            # the agent is not installed or has never run — silence is the honest answer, not a blackout
            return None
        except (OSError, ValueError) as error:
            logger.warning("X728 state file is unreadable: %s", error)
            return None

        state = self._parse(published)
        if state is None:
            return None
        # a stopped agent leaves its last reading behind, and a stale "mains present" would announce the light
        # coming back in the middle of an outage
        if current_time() - state.as_of > self.stale_after:
            logger.warning("X728 state is stale — the host agent stopped publishing at %s", state.as_of)
            return None
        return state

    def _parse(self, published: dict) -> UpsState | None:
        try:
            return UpsState(
                mains_present=published["mains_present"],
                battery_volts=published["battery_volts"],
                battery_percent=published["battery_percent"],
                as_of=datetime.fromisoformat(published["as_of"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            logger.warning("X728 state file does not hold a reading: %s", error)
            return None
