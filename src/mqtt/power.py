"""The Delta 2 on the broker: whether the grid is up, and how much is left if it is not.

A phone has no tile for "mains present", so this arrives as a contact sensor — the shape the rest of the
world uses for the same thing. The station's own charge rides along on it, because during an outage the two
questions are always asked together.
"""
import logging
from collections.abc import Mapping

from src.modules.power.domain import EcoFlowState, GridState
from src.modules.power.mains_monitor import classify_grid
from src.modules.power.services.ecoflow_station import EcoFlowStation
from src.mqtt.surface import MqttContext, MqttSurface

logger = logging.getLogger(__name__)

AVAILABLE = "power/available"
MAINS = "power/mains"
BATTERY = "power/battery"
BATTERY_LOW = "power/battery-low"
CHARGING = "power/charging"

# below this, on battery, the station is close enough to empty that it is worth a badge on the phone
LOW_BATTERY_PERCENT = 20


def render_state(state: EcoFlowState | None) -> dict[str, str]:
    """Turn one Delta 2 reading into the topics a contact sensor with a battery expects."""
    grid = classify_grid(state)
    if state is None or grid is GridState.UNKNOWN:
        # off, shelved, out of ble range — or idle and full, which reads exactly like an outage and must not
        # be published as one. a tile saying "no response" is honest; a tile saying "світло зникло" is not
        return {AVAILABLE: "false"}

    on_grid = grid is GridState.ON_GRID
    return {
        AVAILABLE: "true",
        MAINS: str(on_grid).lower(),
        BATTERY: str(round(state.battery_percent)),
        # low only matters while the grid is down: 20% sitting in storage is not an alarm, 20% mid-outage is
        BATTERY_LOW: str(not on_grid and state.battery_percent < LOW_BATTERY_PERCENT).lower(),
        CHARGING: str(on_grid).lower(),
    }


class PowerReadout:
    """Publishes the station, and nothing more — the conservation decisions stay in the bot."""

    def __init__(self, ecoflow_station: EcoFlowStation):
        self.ecoflow_station = ecoflow_station

    async def read(self) -> Mapping[str, str]:
        # the cached reading on purpose: a ble refresh every half minute would keep the radio busy for nothing
        return render_state(await self.ecoflow_station.read_state())


def register_listeners(surface: MqttSurface, context: MqttContext) -> None:
    """Expose the station only where there is one."""
    settings = context.settings
    if not settings.ECOFLOW_ENABLED or context.ecoflow_station is None:
        return

    readout = PowerReadout(ecoflow_station=context.ecoflow_station)
    surface.publish_every(settings.MQTT_PUBLISH_INTERVAL_SECONDS, readout.read)
