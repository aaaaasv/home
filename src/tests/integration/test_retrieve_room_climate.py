from datetime import timedelta

from src.modules.room_climate.use_cases.retrieve_room_climate import RetrieveRoomClimateUseCase
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase


class RetrieveRoomClimateTestCase(BaseIntegrationTestCase):
    """
    The air of a named room, read from the sensors that stand in it.

    this used to read the wired sht31, which is bolted to the pi and has measured the server shelf ever since
    the pi moved there — so every consumer was told the shelf's air and called it the room's.
    """

    def build_use_case(self) -> RetrieveRoomClimateUseCase:
        return RetrieveRoomClimateUseCase(uow=self.uow, household_calendar=self.household_calendar)

    async def test_retrieve_room_climate_returns_the_newest_reading_of_that_room(self):
        await self.seed_sensor_readings(
            room="спальня",
            temperature_celsius=21.0,
            humidity_percent=44.0,
            since=FROZEN_NOW - timedelta(hours=3),
            until=FROZEN_NOW - timedelta(hours=2),
        )
        await self.seed_sensor_readings(
            room="спальня",
            temperature_celsius=23.5,
            humidity_percent=41.0,
            since=FROZEN_NOW - timedelta(minutes=20),
            until=FROZEN_NOW,
        )

        climate = await self.build_use_case()("спальня")

        self.assertEqual((climate.temperature_celsius, climate.relative_humidity_percent), (23.5, 41.0))

    async def test_retrieve_room_climate_of_a_room_without_sensors_is_nothing(self):
        await self.seed_sensor_readings(
            room="спальня",
            temperature_celsius=21.0,
            humidity_percent=44.0,
            since=FROZEN_NOW - timedelta(minutes=20),
            until=FROZEN_NOW,
        )

        climate = await self.build_use_case()("кухня-вітальня")

        self.assertIsNone(climate)

    async def test_retrieve_room_climate_older_than_six_hours_is_nothing(self):
        await self.seed_sensor_readings(
            room="спальня",
            temperature_celsius=21.0,
            humidity_percent=44.0,
            since=FROZEN_NOW - timedelta(hours=9),
            until=FROZEN_NOW - timedelta(hours=7),
        )

        climate = await self.build_use_case()("спальня")

        self.assertIsNone(climate)

    async def test_retrieve_room_climate_without_a_room_name_is_nothing(self):
        climate = await self.build_use_case()("")

        self.assertIsNone(climate)
