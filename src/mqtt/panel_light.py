"""The switchboard strip on the broker, as the dimmable lamp a phone already knows how to draw.

The automatic half of this light — on when the grid drops, off once the changeover is thrown — lives on the
host and never asks the bot's permission. What appears here is only the hand on it: a tap or a slider, so
the same strip doubles as an ordinary lamp for the corridor.
"""
import logging
from collections.abc import Mapping

from src.modules.lighting.domain import PanelLightState
from src.modules.lighting.services.panel_light import PanelLight
from src.mqtt.surface import MqttContext, MqttSurface

logger = logging.getLogger(__name__)

AVAILABLE = "panel-light/available"
ON = "panel-light/on"
BRIGHTNESS = "panel-light/brightness"
SET_ON = "panel-light/set/on"
SET_BRIGHTNESS = "panel-light/set/brightness"

# what "on" means when a tile is tapped rather than dragged: bright enough to walk a corridor by, well under
# the level that spends the router's pack. the outage light is a tenth of this and lives on the host
TAP_BRIGHTNESS_PERCENT = 20.0


def render_state(state: PanelLightState | None) -> dict[str, str]:
    if state is None:
        # the host service is not answering: a lamp tile frozen on its last value would be a lie
        return {AVAILABLE: "false"}

    return {
        AVAILABLE: "true",
        ON: "true" if state.is_on else "false",
        BRIGHTNESS: f"{state.brightness_percent:.0f}",
    }


class PanelLightControl:
    def __init__(self, panel_light: PanelLight):
        self.panel_light = panel_light

    async def read(self) -> Mapping[str, str]:
        return render_state(await self.panel_light.read())

    async def set_on(self, payload: str) -> Mapping[str, str]:
        wanted_on = payload.strip().lower() in {"true", "1", "on"}
        # a tap carries no level, so it restores the last one only in the sense that off is zero: anything
        # else would need the bot to remember a number the host already owns
        return await self.ask_for(TAP_BRIGHTNESS_PERCENT if wanted_on else 0.0)

    async def set_brightness(self, payload: str) -> Mapping[str, str]:
        try:
            brightness = float(payload)
        except ValueError:
            logger.warning("Ignoring an unreadable brightness: %s", payload)
            return {}

        return await self.ask_for(brightness)

    async def ask_for(self, brightness_percent: float) -> Mapping[str, str]:
        """
        Answer with the level that was asked for, not the one the strip is at this instant.

        the host fades over a second and a half, so reading the file straight back reports the level the
        slider was dragged *from* — and a controller takes that as the truth and snaps the slider back.
        the periodic reading corrects this within the publish interval if the host disagrees.
        """
        brightness_percent = max(0.0, min(100.0, brightness_percent))
        await self.panel_light.set_brightness(brightness_percent)
        return render_state(PanelLightState(is_on=brightness_percent > 0, brightness_percent=brightness_percent))


def register_listeners(surface: MqttSurface, context: MqttContext) -> None:
    """Expose the strip only where the host service is wired in."""
    settings = context.settings
    if not settings.PANEL_LIGHT_ENABLED or context.panel_light is None:
        return

    control = PanelLightControl(panel_light=context.panel_light)
    surface.publish_every(settings.MQTT_PUBLISH_INTERVAL_SECONDS, control.read)
    surface.on_command(SET_ON, control.set_on)
    surface.on_command(SET_BRIGHTNESS, control.set_brightness)
