"""The room sensor on the broker, as the two tiles a phone already knows how to draw.

Whoever configures the controller must label it for where the sensor physically is. Right now that is the
shelf beside the router, not the room — putting "вітальня" on this would spread a comfortable lie onto a
second interface, where it would look even more official than it does in the bot.
"""
from collections.abc import Mapping

from src.modules.room_climate.domain import RoomClimate
from src.modules.room_climate.services.room_climate_sensor import RoomClimateSensor
from src.mqtt.surface import MqttContext, MqttSurface

AVAILABLE = "room-climate/available"
TEMPERATURE = "room-climate/temperature"
HUMIDITY = "room-climate/humidity"


def render_climate(climate: RoomClimate | None) -> dict[str, str]:
    """Turn one reading of the air into the topics a temperature and a humidity tile expect."""
    if climate is None:
        # a sensor that cannot be read must go quiet, not keep the last number standing
        return {AVAILABLE: "false"}

    return {
        AVAILABLE: "true",
        TEMPERATURE: f"{climate.temperature_celsius:.1f}",
        HUMIDITY: f"{climate.relative_humidity_percent:.0f}",
    }


class RoomClimateReadout:
    def __init__(self, room_climate_sensor: RoomClimateSensor):
        self.room_climate_sensor = room_climate_sensor

    async def read(self) -> Mapping[str, str]:
        return render_climate(await self.room_climate_sensor.read())


def register_listeners(surface: MqttSurface, context: MqttContext) -> None:
    """Expose the air only where a sensor is wired in."""
    settings = context.settings
    if not settings.CLIMATE_SENSOR_ENABLED or context.room_climate_sensor is None:
        return

    readout = RoomClimateReadout(room_climate_sensor=context.room_climate_sensor)
    surface.publish_every(settings.MQTT_PUBLISH_INTERVAL_SECONDS, readout.read)
