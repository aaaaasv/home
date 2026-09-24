"""The soil probes on the broker: a jump in moisture is somebody watering, and the bot writes it down itself.

Why this is worth the trouble: «справжні проміжки між поливами» on a plant's sheet are, today, the gaps
between *button presses*. Water a pot and forget to tap, and the record grows a hole that both the schedule
and the photo review then reason from. The probe already knows what the button is asked to say.

What it deliberately does not do: decide anything about the plant. It records care and says so, and the card
it posts carries the same «скасувати» every other record has — a false positive costs one tap.
"""
import json
import logging
from collections.abc import Awaitable, Callable

from src.mqtt.surface import MqttContext, MqttSurface

logger = logging.getLogger(__name__)

WateringRecorder = Callable[[int], Awaitable[None]]


class SoilWatch:
    """
    Remembers where each probe was, so a rise can be told from a level.

    the baseline is the last reading, not an average: watering shows up as one step between two samples
    half an hour apart, and averaging would smear exactly the edge being looked for.
    """

    def __init__(self, plant_by_sensor: dict[str, int], jump_points: float, wet_minimum: float):
        self.plant_by_sensor = plant_by_sensor
        self.jump_points = jump_points
        self.wet_minimum = wet_minimum
        self.last_moisture: dict[str, float] = {}

    def follow(self, sensor: str, recorder: WateringRecorder) -> Callable[[str], Awaitable[None]]:
        async def handle(payload: str) -> None:
            try:
                moisture = float(json.loads(payload)["soil_moisture"])
            except (ValueError, KeyError, TypeError):
                return

            previous = self.last_moisture.get(sensor)
            self.last_moisture[sensor] = moisture
            if previous is None:
                return

            if moisture - previous < self.jump_points or moisture < self.wet_minimum:
                return

            logger.info("%s went %.0f%% -> %.0f%% — that is a watering", sensor, previous, moisture)
            await recorder(self.plant_by_sensor[sensor])

        return handle


def register_listeners(surface: MqttSurface, context: MqttContext) -> None:
    """Follow a probe only where it is mapped to a plant and there is somewhere to record the care."""
    settings = context.settings
    plant_by_sensor = settings.plant_by_soil_sensor
    if not plant_by_sensor or context.record_watering is None:
        return

    watch = SoilWatch(
        plant_by_sensor=plant_by_sensor,
        jump_points=settings.PLANT_SOIL_JUMP_POINTS,
        wet_minimum=settings.PLANT_SOIL_WET_MINIMUM_PERCENT,
    )
    for sensor in plant_by_sensor:
        surface.listen_to(f"{settings.ZIGBEE_TOPIC_PREFIX}/{sensor}", watch.follow(sensor, context.record_watering))
