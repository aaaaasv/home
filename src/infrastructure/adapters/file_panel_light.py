"""The strip on the shelf, reached through the two small files its host service keeps under /run."""
import json
import logging
from pathlib import Path

from src.modules.lighting.domain import PanelLightState

logger = logging.getLogger(__name__)


class FilePanelLight:
    """
    Reads the host service's state file and writes its command file.

    a file rather than a socket because the service must keep working with the bot stopped — an outage at
    four in the morning is exactly when a container might be down, and the light is what gets someone to
    the switchboard. so the automatic path lives entirely on the host, and this is only the hand on it.
    """

    def __init__(self, state_path: Path, command_path: Path):
        self.state_path = state_path
        self.command_path = command_path
        self._was_readable = True

    async def read(self) -> PanelLightState | None:
        """
        The service's last published state, or None when it cannot be read.

        None greys the lamp out in the phone's home app, so it must leave a trace. it used to leave none: the
        one time somebody reached for the tile and found it dead, there was nothing in any log to say why.
        only the change is logged, because a service that is genuinely down would otherwise fill the log at
        the polling interval for as long as it stays down.
        """
        try:
            published = json.loads(self.state_path.read_text())
        except (OSError, ValueError) as error:
            if self._was_readable:
                logger.warning("the panel light state is unreadable, so the lamp goes unavailable: %s", error)
                self._was_readable = False
            # the service is down or has not written yet; saying nothing is better than saying "off"
            return None

        if not self._was_readable:
            logger.info("the panel light state is readable again")
            self._was_readable = True
        return PanelLightState(is_on=bool(published.get("on")), brightness_percent=float(published.get("percent", 0)))

    async def set_brightness(self, brightness_percent: float, minutes: float | None = None) -> None:
        """
        Ask the host for a level, and for how long it may hold it.

        the file is rewritten even when nothing in it changed: the host tells a new request from the
        standing one by when the file was written, because two alerts in an evening ask for the same
        percent and the second one still has to start its own clock.
        """
        brightness_percent = max(0.0, min(100.0, brightness_percent))
        asked = {"percent": round(brightness_percent, 1)}
        if minutes is not None:
            asked["minutes"] = round(minutes, 1)
        try:
            self.command_path.write_text(json.dumps(asked))
        except OSError as error:
            logger.warning("cannot write the panel light command: %s", error)
