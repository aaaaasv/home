from datetime import timedelta

from src.modules.sensors.use_cases.measure_climate_trend import MeasureClimateTrendUseCase
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase

BEDROOM = "temp-bedroom"
KITCHEN = "temp-kitchen"
ROOM_SENSORS = {BEDROOM, KITCHEN}


class MeasureClimateTrendTestCase(BaseIntegrationTestCase):
    """
    Comparing the flat with itself, where the whole difficulty is picking windows that are comparable.

    the first version compared today-so-far with a whole yesterday, which reads colder every morning for no
    reason but the hour — so the rolling day is the thing under test here, not just the arithmetic.
    """

    def measure(self):
        return MeasureClimateTrendUseCase(uow=self.uow, household_calendar=self.household_calendar)(ROOM_SENSORS)

    async def seed_window(self, hours_ago_from: int, hours_ago_to: int, temperature: float, humidity: float = 50.0):
        await self.seed_sensor_readings(
            room="спальня",
            sensor=BEDROOM,
            since=FROZEN_NOW - timedelta(hours=hours_ago_from),
            until=FROZEN_NOW - timedelta(hours=hours_ago_to),
            temperature_celsius=temperature,
            humidity_percent=humidity,
        )

    async def test_measure_reports_the_flat_cooling_against_the_previous_day(self):
        await self.seed_window(48, 25, temperature=24.0)
        await self.seed_window(23, 0, temperature=22.0)

        trend = await self.measure()

        self.assertEqual(round(trend.temperature_change_since_yesterday, 1), -2.0)

    async def test_measure_reports_the_flat_warming_against_the_previous_day(self):
        await self.seed_window(48, 25, temperature=20.0)
        await self.seed_window(23, 0, temperature=21.5)

        trend = await self.measure()

        self.assertEqual(round(trend.temperature_change_since_yesterday, 1), 1.5)

    async def test_measure_compares_windows_of_the_same_length_whatever_the_hour(self):
        """A cold night must not read as a cooling flat: both windows are a full rolling day."""
        async with self.uow as uow:
            for hours_ago in range(1, 49):
                await uow.sensor_readings.create(
                    {
                        "sensor": BEDROOM,
                        "room": "спальня",
                        "temperature_celsius": 18.0 if hours_ago % 24 < 8 else 25.0,
                        "relative_humidity_percent": 50.0,
                        "measured_at": FROZEN_NOW - timedelta(hours=hours_ago),
                    }
                )

        trend = await self.measure()

        self.assertEqual(trend.temperature_change_since_yesterday, 0.0)

    async def test_measure_reports_the_air_drying_out_against_the_previous_day(self):
        await self.seed_window(48, 25, temperature=22.0, humidity=58.0)
        await self.seed_window(23, 0, temperature=22.0, humidity=43.0)

        trend = await self.measure()

        self.assertEqual(round(trend.humidity_change_since_yesterday, 1), -15.0)

    async def test_measure_says_nothing_about_a_day_it_has_no_readings_for(self):
        await self.seed_window(23, 0, temperature=22.0)

        trend = await self.measure()

        self.assertIsNone(trend.temperature_change_since_yesterday)

    async def test_measure_compares_the_rolling_day_with_the_folded_week(self):
        await self.seed_window(23, 0, temperature=25.0)
        async with self.uow as uow:
            for day_offset in range(1, 6):
                await uow.sensor_days.save_day(
                    BEDROOM,
                    self.household_calendar.today() - timedelta(days=day_offset),
                    {
                        "room": "спальня",
                        "reading_count": 100,
                        "average_temperature_celsius": 21.0,
                        "average_humidity_percent": 50.0,
                    },
                )

        trend = await self.measure()

        self.assertEqual(round(trend.temperature_change_since_last_week, 1), 4.0)

    async def test_measure_ignores_a_folded_day_the_sensors_barely_spoke_on(self):
        """A day with three readings averages whatever those three minutes happened to be."""
        await self.seed_window(23, 0, temperature=25.0)
        async with self.uow as uow:
            await uow.sensor_days.save_day(
                BEDROOM,
                self.household_calendar.today() - timedelta(days=2),
                {
                    "room": "спальня",
                    "reading_count": 3,
                    "average_temperature_celsius": 5.0,
                    "average_humidity_percent": 50.0,
                },
            )

        trend = await self.measure()

        self.assertIsNone(trend.temperature_change_since_last_week)
