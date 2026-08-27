from src.common.use_case import BaseUseCase
from src.modules.room_climate.domain import RoomClimate


class RetrieveRoomClimateUseCase(BaseUseCase):
    async def __call__(self) -> RoomClimate | None:
        async with self.uow as uow:
            reading = await uow.room_climate_readings.retrieve_latest()
            if reading is None:
                return None

            return RoomClimate(
                temperature_celsius=reading.temperature_celsius,
                relative_humidity_percent=reading.relative_humidity_percent,
            )
