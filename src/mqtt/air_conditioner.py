"""The air conditioner as a thermostat on the broker — what a controller turns into a tile on a phone.

This only translates. Every decision still belongs to the bot: what arrives here is a tap on a tile, never
an automation, so the house never grows a second brain that nobody can debug.
"""
import logging
from collections.abc import Mapping

from src.common.config import Settings
from src.modules.air_conditioner.domain import AirConditionerMode, AirConditionerState
from src.modules.air_conditioner.services.air_conditioner import AirConditioner
from src.mqtt.surface import MqttContext, MqttSurface

logger = logging.getLogger(__name__)

AVAILABLE = "air-conditioner/available"
CURRENT_STATE = "air-conditioner/current-state"
TARGET_STATE = "air-conditioner/target-state"
CURRENT_TEMPERATURE = "air-conditioner/current-temperature"
TARGET_TEMPERATURE = "air-conditioner/target-temperature"
SET_TARGET_STATE = "air-conditioner/set/target-state"
SET_TARGET_TEMPERATURE = "air-conditioner/set/target-temperature"

# a thermostat knows four states and the unit knows five modes, so drying and fan-only — which no thermostat
# can express — read as "auto". nothing is applied from that reading: a mode changes only when someone asks
TARGET_STATE_BY_MODE = {
    AirConditionerMode.COOL: "cool",
    AirConditionerMode.HEAT: "heat",
    AirConditionerMode.AUTO: "auto",
    AirConditionerMode.DRY: "auto",
    AirConditionerMode.FAN: "auto",
}
MODE_BY_TARGET_STATE = {
    "cool": AirConditionerMode.COOL,
    "heat": AirConditionerMode.HEAT,
    "auto": AirConditionerMode.AUTO,
}


def render_state(state: AirConditionerState | None) -> dict[str, str]:
    """Turn one reading of the unit into the topics a thermostat controller expects."""
    if state is None:
        # the unit did not answer: say so, or a split that is off the network reads as a split that is off
        return {AVAILABLE: "false"}

    readings = {
        AVAILABLE: "true",
        CURRENT_STATE: render_current_state(state),
        TARGET_STATE: TARGET_STATE_BY_MODE[state.mode] if state.is_on else "off",
        TARGET_TEMPERATURE: str(state.target_temperature_celsius),
    }
    # the unit's own sensor sits high on the wall and reads warm, but it is at least in the right room —
    # the sht31 is on the server shelf until it is replaced
    if state.room_temperature_celsius is not None:
        readings[CURRENT_TEMPERATURE] = str(state.room_temperature_celsius)
    return readings


def render_current_state(state: AirConditionerState) -> str:
    """What the unit is doing right now, in the three words a thermostat has for it."""
    if not state.is_on:
        return "off"
    # a thermostat reports only heating or cooling, so drying, fan-only and auto all read as cooling
    return "heat" if state.mode is AirConditionerMode.HEAT else "cool"


class AirConditionerControl:
    """Publishes the unit as a thermostat and applies what a controller sets on it."""

    def __init__(self, air_conditioner: AirConditioner, settings: Settings):
        self.air_conditioner = air_conditioner
        self.settings = settings

    async def read(self) -> Mapping[str, str]:
        return render_state(await self.air_conditioner.read_state())

    async def set_target_state(self, payload: str) -> Mapping[str, str]:
        wanted = payload.strip().lower()
        if wanted == "off":
            return render_state(await self.air_conditioner.apply(is_on=False))

        mode = MODE_BY_TARGET_STATE.get(wanted)
        if mode is None:
            logger.warning("Ignoring an unknown thermostat state: %s", payload)
            return {}
        return render_state(await self.air_conditioner.apply(is_on=True, mode=mode))

    async def set_target_temperature(self, payload: str) -> Mapping[str, str]:
        # a thermostat dial sends half degrees, and the unit takes whole ones
        try:
            wanted = round(float(payload))
        except ValueError:
            logger.warning("Ignoring an unreadable target temperature: %s", payload)
            return {}

        target = min(
            max(wanted, self.settings.AIR_CONDITIONER_MIN_TEMPERATURE),
            self.settings.AIR_CONDITIONER_MAX_TEMPERATURE,
        )
        return render_state(await self.air_conditioner.apply(target_temperature_celsius=target))


def register_listeners(surface: MqttSurface, context: MqttContext) -> None:
    """Expose the unit only where there is one — a flat without a split publishes nothing."""
    settings = context.settings
    if not settings.AIR_CONDITIONER_ENABLED or context.air_conditioner is None:
        return

    control = AirConditionerControl(air_conditioner=context.air_conditioner, settings=settings)
    # a controller must show "no response" when the bot dies, not a tile frozen on the last reading it saw
    surface.announce_loss_as(AVAILABLE, "false")
    surface.publish_every(settings.MQTT_PUBLISH_INTERVAL_SECONDS, control.read)
    surface.on_command(SET_TARGET_STATE, control.set_target_state)
    surface.on_command(SET_TARGET_TEMPERATURE, control.set_target_temperature)
