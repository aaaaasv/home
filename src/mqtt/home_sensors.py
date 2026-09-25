"""Every sensor on the broker, written down — so that a question about last week has somewhere to look.

Zigbee2MQTT holds one value per device and nothing before it, and until now the bot held nothing at all. The
cost of that was concrete: the night the shower was measured, the readings had to be collected into a file by
hand, because nothing in the house remembered what the air had done an hour earlier.

This listens rather than polls, because the sensors report on change: a reading arrives when something
happened, which is exactly when it is worth keeping.
"""
import json
import logging
from collections.abc import Awaitable, Callable

from src.modules.sensors.commands import RecordSensorReadingCommand
from src.mqtt.surface import MqttContext, MqttSurface

logger = logging.getLogger(__name__)

ReadingRecorder = Callable[[RecordSensorReadingCommand], Awaitable[None]]


def read_measurement(payload: str, sensor: str, room: str | None) -> RecordSensorReadingCommand:
    """Take from a device message the four things worth keeping, and let the rest of its keys pass."""
    message = json.loads(payload)
    return RecordSensorReadingCommand(
        sensor=sensor,
        room=room,
        temperature_celsius=_number(message.get("temperature")),
        relative_humidity_percent=_number(message.get("humidity")),
        soil_moisture_percent=_number(message.get("soil_moisture")),
        battery_percent=_number(message.get("battery")),
    )


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def follow(sensor: str, room: str | None, record: ReadingRecorder):
    async def handle(payload: str) -> None:
        try:
            measurement = read_measurement(payload, sensor, room)
        except (ValueError, TypeError):
            logger.warning("%s sent something that is not a reading", sensor)
            return

        await record(measurement)

    return handle


def register_listeners(surface: MqttSurface, context: MqttContext) -> None:
    """Follow every sensor the settings name, and nothing else."""
    settings = context.settings
    if context.record_sensor_reading is None:
        return

    for sensor, room in settings.recorded_sensors.items():
        surface.listen_to(
            f"{settings.ZIGBEE_TOPIC_PREFIX}/{sensor}",
            follow(sensor, room, context.record_sensor_reading),
        )
