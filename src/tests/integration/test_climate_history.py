from datetime import date, timedelta

from src.modules.weather.use_cases.compose_climate_history import ComposeClimateHistoryUseCase
from src.tests.integration.base import BaseIntegrationTestCase

ROOMS = frozenset({"спальня", "ванна", "коридор"})


class ClimateDaysSeeding:
    """The two daily records as rows, for whoever needs a month of them laid down."""

    async def seed_room_day(self, room: str, day: date, low: float, high: float, humidity=50.0, readings=24):
        async with self.uow as uow:
            await uow.sensor_days.save_day(
                f"temp-{room}",
                day,
                {
                    "room": room,
                    "reading_count": readings,
                    "minimum_temperature_celsius": low,
                    "maximum_temperature_celsius": high,
                    "average_temperature_celsius": (low + high) / 2,
                    "minimum_humidity_percent": humidity,
                    "maximum_humidity_percent": humidity,
                    "average_humidity_percent": humidity,
                },
            )

    async def seed_outdoor_day(self, day: date, low: float, high: float, humidity=80.0, readings=24):
        async with self.uow as uow:
            await uow.outdoor_weather_days.save_day(
                day,
                {
                    "reading_count": readings,
                    "minimum_temperature_celsius": low,
                    "maximum_temperature_celsius": high,
                    "average_temperature_celsius": (low + high) / 2,
                    "minimum_humidity_percent": humidity,
                    "maximum_humidity_percent": humidity,
                    "average_humidity_percent": humidity,
                },
            )


class ClimateHistoryTestCase(ClimateDaysSeeding, BaseIntegrationTestCase):
    """
    The month behind us, as the two daily records the chart draws.

    the flat speaks as the median of its rooms: one sensor over a radiator, or a bathroom after a shower,
    must not be able to carry the line the whole house is read from.
    """

    async def compose(self, days: int = 30):
        return await ComposeClimateHistoryUseCase(uow=self.uow, household_calendar=self.household_calendar)(
            days=days, rooms=ROOMS
        )

    async def test_compose_with_three_rooms_reports_the_middle_one_for_every_number(self):
        yesterday = self.today - timedelta(days=1)
        await self.seed_room_day("спальня", yesterday, low=21.0, high=23.0)
        await self.seed_room_day("ванна", yesterday, low=23.0, high=26.0)
        await self.seed_room_day("коридор", yesterday, low=22.0, high=24.0)

        history = await self.compose()

        self.assertEqual(
            [(day.day, day.minimum_celsius, day.maximum_celsius, day.average_celsius) for day in history.indoor],
            [(yesterday, 22.0, 24.0, 23.0)],
        )

    async def test_compose_leaves_today_out_because_the_day_is_not_over(self):
        """Read at eight in the morning, today's average is the night — a false dip at the right edge."""
        await self.seed_room_day("спальня", self.today, low=22.0, high=24.0)
        await self.seed_outdoor_day(self.today, low=5.0, high=11.0)

        history = await self.compose()

        self.assertEqual((history.indoor, history.outdoor), ((), ()))

    async def test_compose_leaves_out_a_day_the_sensor_barely_spoke_on(self):
        yesterday = self.today - timedelta(days=1)
        await self.seed_room_day("спальня", yesterday, low=22.0, high=24.0, readings=3)

        history = await self.compose()

        self.assertEqual(history.indoor, ())

    async def test_compose_keeps_the_sky_for_a_day_no_room_reported(self):
        """The two records start on different days and the chart draws each as long as it is."""
        yesterday = self.today - timedelta(days=1)
        await self.seed_outdoor_day(yesterday, low=5.0, high=11.0)

        history = await self.compose()

        self.assertEqual([(day.day, day.average_celsius) for day in history.outdoor], [(yesterday, 8.0)])
        self.assertEqual(history.indoor, ())

    async def test_compose_reads_the_middle_room_for_humidity_too(self):
        yesterday = self.today - timedelta(days=1)
        await self.seed_room_day("спальня", yesterday, low=22.0, high=24.0, humidity=40.0)
        await self.seed_room_day("ванна", yesterday, low=22.0, high=24.0, humidity=70.0)
        await self.seed_room_day("коридор", yesterday, low=22.0, high=24.0, humidity=45.0)

        history = await self.compose()

        self.assertEqual([day.average_humidity_percent for day in history.indoor], [45.0])

    async def test_compose_stops_at_the_window_it_was_asked_for(self):
        for position in range(1, 8):
            await self.seed_outdoor_day(self.today - timedelta(days=position), low=5.0, high=11.0)

        history = await self.compose(days=3)

        self.assertEqual(
            [day.day for day in history.outdoor],
            [self.today - timedelta(days=position) for position in (3, 2, 1)],
        )

    async def test_compose_with_nothing_recorded_is_empty(self):
        history = await self.compose()

        self.assertTrue(history.is_empty)
