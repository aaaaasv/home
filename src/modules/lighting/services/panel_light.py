from typing import Protocol

from src.modules.lighting.domain import PanelLightState


class PanelLight(Protocol):
    """
    The strip on the server shelf, aimed at the switchboard.

    the bot never drives the pin: a container may not, and the light has to work during an outage whether
    or not docker came up. the host service owns the gpio, and this is only the way to ask it.
    """

    async def read(self) -> PanelLightState | None:
        """What the strip is doing, or None when the host service is not answering."""
        ...

    async def set_brightness(self, brightness_percent: float) -> None:
        """Ask for a level; zero is off. The host fades to it."""
        ...
