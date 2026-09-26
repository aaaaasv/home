"""What the air and the earth around one plant are doing, for the card a person actually opens.

The pot is not the room. Measured on 25.09.2026: 19,4 °C in Mister Big's pot against 24,6 on the shelf in
the hall — five degrees, which is the difference between a plant that is merely cool and one that is being
kept below the species' floor all winter. So a plant with a probe of its own is judged and shown by it, and
a plant without one falls back to its room's air **named as the room**, so nobody reads it as the pot's.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.common.time import as_utc
from src.infrastructure.db.uow import UnitOfWork

# a probe reports on change and a pot changes slowly, so silence is normal for hours — but a day of it is
# a flat battery, and a number that old must not sit on a card as if it were current
STALE_AFTER = timedelta(hours=12)


@dataclass(frozen=True)
class PlantAir:
    """Where the numbers came from matters as much as the numbers, so the source is part of the answer."""

    temperature_celsius: float | None
    relative_humidity_percent: float | None
    soil_moisture_percent: float | None
    measured_at: datetime
    room: str | None


async def read_plant_air(uow: UnitOfWork, sensor: str | None, room: str | None, now: datetime) -> PlantAir | None:
    if sensor is not None:
        reading = await uow.sensor_readings.retrieve_latest(sensor)
        if reading is not None and now - as_utc(reading.measured_at) <= STALE_AFTER:
            return PlantAir(
                temperature_celsius=reading.temperature_celsius,
                relative_humidity_percent=reading.relative_humidity_percent,
                soil_moisture_percent=reading.soil_moisture_percent,
                measured_at=as_utc(reading.measured_at),
                room=None,
            )

    if room is None:
        return None

    readings = await uow.sensor_readings.list_room_measured_since(room, now - STALE_AFTER)
    if not readings:
        return None
    newest = readings[-1]
    return PlantAir(
        temperature_celsius=newest.temperature_celsius,
        relative_humidity_percent=newest.relative_humidity_percent,
        soil_moisture_percent=None,
        measured_at=as_utc(newest.measured_at),
        room=room,
    )
