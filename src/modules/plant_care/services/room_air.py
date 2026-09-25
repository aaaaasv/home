"""What a room's air has been doing lately, as the comfort rules need it: a median, not a last reading.

A plant is judged on a median over hours rather than on the newest number, because a kettle, a shower or a
window opened for five minutes all move a single sample far enough to cross a threshold. The same reading
that makes a plant look uncomfortable makes it look fine again twenty minutes later, and a card that appears
and disappears is worse than no card.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from src.infrastructure.db.models import SensorReading
from src.infrastructure.db.uow import UnitOfWork


@dataclass(frozen=True)
class RoomAir:
    temperature_celsius: float
    relative_humidity_percent: float


async def read_air_by_room(
    uow: UnitOfWork, rooms: set[str], window_start: datetime, alert_window_hours: int
) -> dict[str, RoomAir]:
    """
    A room appears in the answer only when its sensors covered the whole window.

    a room whose sensor went flat an hour ago has no entry rather than a stale one: a battery that died is a
    reason to say nothing about that room's plants, never a reason to judge them on yesterday's air.
    """
    air: dict[str, RoomAir] = {}
    for room in rooms:
        readings = await uow.sensor_readings.list_room_measured_since(room, window_start)
        if not _covers_the_whole_window(readings, alert_window_hours):
            continue

        temperatures = [reading.temperature_celsius for reading in readings if reading.temperature_celsius is not None]
        humidities = [
            reading.relative_humidity_percent for reading in readings if reading.relative_humidity_percent is not None
        ]
        if not temperatures or not humidities:
            continue

        air[room] = RoomAir(temperature_celsius=median(temperatures), relative_humidity_percent=median(humidities))
    return air


def _covers_the_whole_window(readings: list[SensorReading], alert_window_hours: int) -> bool:
    if len(readings) < 2:
        return False

    measured_span = readings[-1].measured_at - readings[0].measured_at
    return measured_span >= timedelta(hours=alert_window_hours) * 0.9
