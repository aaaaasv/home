from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.sensors.commands import RecordSensorReadingCommand


class RecordSensorReadingUseCase(BaseUseCase):
    """
    Writes down one measurement, and nothing else.

    deliberately only an insert: the sensors report on change, so this runs tens of times an hour, and folding
    or pruning here would re-read a growing day on every message a battery sensor sends. both belong to the
    hourly fold, which can afford to look at the whole day once.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, data: RecordSensorReadingCommand) -> None:
        if self._says_nothing(data):
            return

        async with self.uow as uow:
            # the moment the reading arrived, not the moment the device thinks it is: the delay is seconds
            await uow.sensor_readings.create(data.model_dump() | {"measured_at": self.household_calendar.now()})

    def _says_nothing(self, data: RecordSensorReadingCommand) -> bool:
        """A device message that carries no measurement — a heartbeat, a config echo — is not a reading."""
        return (
            data.temperature_celsius is None
            and data.relative_humidity_percent is None
            and data.soil_moisture_percent is None
            and data.battery_percent is None
        )
