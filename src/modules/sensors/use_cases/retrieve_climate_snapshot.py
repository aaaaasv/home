from datetime import timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.time import as_utc
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.sensors.domain import ClimateSnapshot, SensorNow

# a sensor reports on change, so silence is normal — but a room that has said nothing all day has a flat battery
# rather than perfectly steady air, and a number that old must not be shown as if it were current
STALE_AFTER = timedelta(hours=6)


class RetrieveClimateSnapshotUseCase(BaseUseCase):
    """
    What every sensor is saying right now, room air apart from soil.

    the two are not one list because they answer different questions. room air is about the flat and averages
    across rooms honestly; a probe standing in a pot speaks for that pot alone, and averaging a wet pot with a
    dry one produces a number that describes nowhere.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar, rooms: dict[str, str]):
        super().__init__(uow)
        self.household_calendar = household_calendar
        self.rooms = rooms

    async def __call__(self, soil_sensors: set[str]) -> ClimateSnapshot:
        moment = self.household_calendar.now()
        async with self.uow as uow:
            names = await uow.sensor_readings.list_sensors_measured_since(moment - timedelta(days=30))
            latest = [await uow.sensor_readings.retrieve_latest(name) for name in names]

        air: list[SensorNow] = []
        soil: list[SensorNow] = []
        for reading in latest:
            if reading is None:
                continue
            measured_at = as_utc(reading.measured_at)
            now = SensorNow(
                sensor=reading.sensor,
                room=reading.room or self.rooms.get(reading.sensor),
                measured_at=measured_at,
                temperature_celsius=reading.temperature_celsius,
                relative_humidity_percent=reading.relative_humidity_percent,
                soil_moisture_percent=reading.soil_moisture_percent,
                battery_percent=reading.battery_percent,
                is_stale=moment - measured_at > STALE_AFTER,
            )
            (soil if reading.sensor in soil_sensors else air).append(now)

        return ClimateSnapshot(
            air=sorted(air, key=lambda one: (one.room or "", one.sensor)),
            soil=sorted(soil, key=lambda one: one.sensor),
            taken_at=moment,
        )
