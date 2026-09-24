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

    async def read(self) -> PanelLightState | None:
        try:
            published = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            # the service is down or has not written yet; saying nothing is better than saying "off"
            return None
        return PanelLightState(is_on=bool(published.get("on")), brightness_percent=float(published.get("percent", 0)))

    async def set_brightness(self, brightness_percent: float) -> None:
        brightness_percent = max(0.0, min(100.0, brightness_percent))
        try:
            self.command_path.write_text(json.dumps({"percent": round(brightness_percent, 1)}))
        except OSError as error:
            logger.warning("cannot write the panel light command: %s", error)
