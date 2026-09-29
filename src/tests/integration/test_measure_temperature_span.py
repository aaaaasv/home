from datetime import timedelta

from src.modules.sensors.domain import TemperatureSpan
from src.modules.sensors.use_cases.measure_temperature_span import MeasureTemperatureSpanUseCase
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase

BEDROOM = "temp-bedroom"
KITCHEN = "temp-kitchen"


class MeasureTemperatureSpanTestCase(BaseIntegrationTestCase):
    """The day's low and high, over a rolling day so the hour of asking cannot hide the afternoon."""

    def measure(self, sensors: set[str]):
        return MeasureTemperatureSpanUseCase(uow=self.uow, household_calendar=self.household_calendar)(sensors)

    async def record(self, sensor: str, hours_ago: int, temperature: float | None) -> None:
        async with self.uow as uow:
            await uow.sensor_readings.create(
                {
                    "sensor": sensor,
                    "room": "спальня",
                    "temperature_celsius": temperature,
                    "relative_humidity_percent": 50.0,
                    "measured_at": FROZEN_NOW - timedelta(hours=hours_ago),
                }
            )

    async def test_measure_reports_the_lowest_and_highest_temperature_of_the_last_day(self):
        await self.record(BEDROOM, 20, 21.2)
        await self.record(BEDROOM, 10, 26.4)
        await self.record(BEDROOM, 2, 23.0)

        spans = await self.measure({BEDROOM})

        self.assertEqual(spans, {BEDROOM: TemperatureSpan(sensor=BEDROOM, minimum_celsius=21.2, maximum_celsius=26.4)})

    async def test_measure_ignores_readings_older_than_a_day(self):
        await self.record(BEDROOM, 30, 12.0)
        await self.record(BEDROOM, 5, 22.0)

        spans = await self.measure({BEDROOM})

        self.assertEqual(spans, {BEDROOM: TemperatureSpan(sensor=BEDROOM, minimum_celsius=22.0, maximum_celsius=22.0)})

    async def test_measure_keeps_each_sensor_to_its_own_readings(self):
        await self.record(BEDROOM, 5, 21.0)
        await self.record(KITCHEN, 5, 27.0)

        spans = await self.measure({BEDROOM, KITCHEN})

        self.assertEqual(
            spans,
            {
                BEDROOM: TemperatureSpan(sensor=BEDROOM, minimum_celsius=21.0, maximum_celsius=21.0),
                KITCHEN: TemperatureSpan(sensor=KITCHEN, minimum_celsius=27.0, maximum_celsius=27.0),
            },
        )

    async def test_measure_gives_no_span_to_a_sensor_that_reported_no_temperature(self):
        await self.record(BEDROOM, 5, None)

        spans = await self.measure({BEDROOM})

        self.assertEqual(spans, {})

    async def test_measure_gives_no_span_to_a_sensor_silent_for_a_day(self):
        await self.record(BEDROOM, 40, 20.0)

        spans = await self.measure({BEDROOM})

        self.assertEqual(spans, {})
