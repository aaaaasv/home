from datetime import timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.room_climate.domain import RoomClimate

# a zigbee sensor reports on change, so an hour of silence is ordinary air holding still. half a day of it is a
# flat battery, and a number that old must not be handed to the air conditioner as if it were the room right now
STALE_AFTER = timedelta(hours=6)


class RetrieveRoomClimateUseCase(BaseUseCase):
    """
    The air of one named room, as the sensors standing in it last reported.

    it reads the zigbee series rather than the wired sht31 on purpose. that sensor is bolted to the pi by a short
    i2c ribbon, so it has measured the server shelf since the pi moved there — and a plausible wrong number is
    worse than none, because nobody goes looking for it.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, room: str) -> RoomClimate | None:
        if not room:
            return None

        moment = self.household_calendar.now()
        async with self.uow as uow:
            readings = await uow.sensor_readings.list_room_measured_since(room, moment - STALE_AFTER)

        for reading in reversed(readings):
            if reading.temperature_celsius is not None and reading.relative_humidity_percent is not None:
                return RoomClimate(
                    temperature_celsius=reading.temperature_celsius,
                    relative_humidity_percent=reading.relative_humidity_percent,
                )
        return None
