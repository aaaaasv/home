from datetime import timedelta

from src.modules.room_climate.domain import RoomClimate
from src.modules.room_climate.use_cases.record_room_climate import RecordRoomClimateUseCase
from src.tests.fakes import FixedRoomClimateSensor
from src.tests.integration.base import BaseIntegrationTestCase

RETENTION_HOURS = 48


class RecordRoomClimateTestCase(BaseIntegrationTestCase):
    """
    The wired sensor's own series, which the digest, the air-conditioner card and the herbarium chart read.

    it used to be written from inside the plant comfort rules, which is why every plant was judged by whichever
    room the pi was standing in. the series survives the split; the judging left.
    """

    def build_use_case(self, temperature: float | None, humidity: float | None) -> RecordRoomClimateUseCase:
        climate = None
        if temperature is not None and humidity is not None:
            climate = RoomClimate(temperature_celsius=temperature, relative_humidity_percent=humidity)

        return RecordRoomClimateUseCase(
            uow=self.uow,
            sensor=FixedRoomClimateSensor(climate),
            household_calendar=self.household_calendar,
            retention_hours=RETENTION_HOURS,
        )

    async def test_record_room_climate_stores_the_reading_stamped_with_the_household_clock(self):
        await self.build_use_case(temperature=25.0, humidity=44.0)()

        async with self.uow as uow:
            reading = await uow.room_climate_readings.retrieve_latest()

        self.assertEqual(reading.temperature_celsius, 25.0)
        self.assertEqual(reading.relative_humidity_percent, 44.0)
        self.assertEqual(reading.measured_at, self.household_calendar.now())

    async def test_record_room_climate_without_a_sensor_reading_stores_nothing(self):
        await self.build_use_case(temperature=None, humidity=None)()

        async with self.uow as uow:
            reading = await uow.room_climate_readings.retrieve_latest()

        self.assertEqual(reading, None)

    async def test_record_room_climate_folds_the_day_into_a_summary_that_outlives_the_raw_readings(self):
        await self.build_use_case(temperature=25.0, humidity=44.0)()

        async with self.uow as uow:
            days = await uow.room_climate_days.list_between(self.today, self.today)

        self.assertEqual([day.day for day in days], [self.today])
        self.assertEqual(days[0].average_temperature_celsius, 25.0)
        self.assertEqual(days[0].average_humidity_percent, 44.0)

    async def test_record_room_climate_rewrites_the_day_as_more_readings_arrive(self):
        await self.build_use_case(temperature=20.0, humidity=40.0)()

        await self.build_use_case(temperature=30.0, humidity=60.0)()

        async with self.uow as uow:
            days = await uow.room_climate_days.list_between(self.today, self.today)
        self.assertEqual(len(days), 1)
        self.assertEqual(days[0].minimum_temperature_celsius, 20.0)
        self.assertEqual(days[0].maximum_temperature_celsius, 30.0)
        self.assertEqual(days[0].average_temperature_celsius, 25.0)

    async def test_record_room_climate_prunes_readings_past_the_retention_window(self):
        await self.seed_room_climate_readings(
            humidity_percent=50.0,
            temperature_celsius=21.0,
            since=self.household_calendar.now() - timedelta(hours=RETENTION_HOURS + 2),
            until=self.household_calendar.now() - timedelta(hours=RETENTION_HOURS + 1),
        )

        await self.build_use_case(temperature=25.0, humidity=44.0)()

        async with self.uow as uow:
            readings = await uow.room_climate_readings.list_measured_since(
                self.household_calendar.now() - timedelta(days=30)
            )
        self.assertEqual([reading.temperature_celsius for reading in readings], [25.0])
