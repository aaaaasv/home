from datetime import timedelta
from statistics import mean

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.room_climate.services.room_climate_sensor import RoomClimateSensor


class RecordRoomClimateUseCase(BaseUseCase):
    """
    Polls the wired sensor and keeps its series: a rolling raw table and one summary row per household day.

    this used to live inside the plant comfort rules, which made one sensor's reading and every plant's verdict
    the same act — so the plants could only ever be judged by whichever room the pi happened to be standing in.
    the two are separate now: this owns the series, and comfort is decided per room from what the zigbee sensors
    report. the series stays because the digest, the air-conditioner card and the herbarium chart all read it.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        sensor: RoomClimateSensor,
        household_calendar: HouseholdCalendar,
        retention_hours: int,
    ):
        super().__init__(uow)
        self.sensor = sensor
        self.household_calendar = household_calendar
        self.retention_hours = retention_hours

    async def __call__(self) -> None:
        climate = await self.sensor.read()
        if climate is None:
            return

        # the calendar, not the wall clock: it is the one thing allowed to say what "now" and "today" are
        measured_at = self.household_calendar.now()
        async with self.uow as uow:
            await uow.room_climate_readings.create(
                {
                    "temperature_celsius": climate.temperature_celsius,
                    "relative_humidity_percent": climate.relative_humidity_percent,
                    "measured_at": measured_at,
                }
            )
            # fold today into its one summary row *before* pruning, or the day would be thrown away unrecorded
            await self._summarise_day(uow)
            await uow.room_climate_readings.delete_measured_before(measured_at - timedelta(hours=self.retention_hours))

    async def _summarise_day(self, uow: UnitOfWork) -> None:
        """
        Rewrites today's summary from the raw readings that are still there.

        recomputing beats accumulating a running mean: the raw table keeps more than a household day, so a whole
        day is always present, and a rewrite cannot drift the way an incremental average can.
        """
        day = self.household_calendar.local_date(self.household_calendar.now())
        readings = await uow.room_climate_readings.list_measured_since(self.household_calendar.start_of_day(day))
        if not readings:
            return

        temperatures = [reading.temperature_celsius for reading in readings]
        humidities = [reading.relative_humidity_percent for reading in readings]
        await uow.room_climate_days.save_day(
            day,
            {
                "minimum_temperature_celsius": min(temperatures),
                "maximum_temperature_celsius": max(temperatures),
                "average_temperature_celsius": mean(temperatures),
                "minimum_humidity_percent": min(humidities),
                "maximum_humidity_percent": max(humidities),
                "average_humidity_percent": mean(humidities),
            },
        )
