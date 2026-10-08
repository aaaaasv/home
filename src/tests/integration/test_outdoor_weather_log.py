from datetime import timedelta

from src.infrastructure.db.uow import UnitOfWork
from src.modules.weather.domain import WeatherReport
from src.modules.weather.use_cases.record_outdoor_weather import RecordOutdoorWeatherUseCase
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase


def build_report(temperature: float, humidity: float | None = 60.0) -> WeatherReport:
    return WeatherReport(
        temperature_celsius=temperature,
        apparent_temperature_celsius=None,
        relative_humidity_percent=humidity,
        temperature_max_celsius=temperature,
        temperature_min_celsius=temperature,
        temperature_evening_celsius=None,
        uv_index_max=None,
        is_thunderstorm_expected=False,
        wind_speed_meters_per_second=None,
        precipitation_probability_percent=None,
        rain_window=None,
        european_air_quality_index=None,
        pm2_5_micrograms=None,
        pollen=[],
    )


class RecordOutdoorWeatherTestCase(BaseIntegrationTestCase):
    """
    One row a day for the air outside, folded from hourly samples.

    the indoor side has been kept per room per day for a while; the outdoor side was fetched for every
    digest and dropped, and without the pair nothing about this flat's heat is computable. a day that was
    not recorded cannot be recorded later, which is why this is written before anything reads it.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    async def record(self, *reports: WeatherReport) -> None:
        for report in reports:
            await RecordOutdoorWeatherUseCase(uow=self.uow_factory(), household_calendar=self.household_calendar)(
                report
            )

    async def today_row(self):
        async with self.uow_factory() as uow:
            return await uow.outdoor_weather_days.retrieve_day(self.household_calendar.today())

    async def test_the_first_reading_of_a_day_opens_its_row(self):
        await self.record(build_report(temperature=11.0, humidity=72.0))

        day = await self.today_row()
        self.assertEqual(day.reading_count, 1)
        self.assertEqual(day.minimum_temperature_celsius, 11.0)
        self.assertEqual(day.maximum_temperature_celsius, 11.0)
        self.assertEqual(day.average_temperature_celsius, 11.0)
        self.assertEqual(day.minimum_humidity_percent, 72.0)

    async def test_further_readings_widen_the_day_rather_than_replacing_it(self):
        await self.record(build_report(11.0), build_report(17.0), build_report(8.0))

        day = await self.today_row()
        self.assertEqual(day.reading_count, 3)
        self.assertEqual(day.minimum_temperature_celsius, 8.0)
        self.assertEqual(day.maximum_temperature_celsius, 17.0)
        self.assertEqual(day.average_temperature_celsius, 12.0)

    async def test_the_average_is_a_running_mean_so_the_day_keeps_no_readings(self):
        await self.record(*(build_report(temperature) for temperature in (10.0, 20.0, 30.0, 40.0)))

        day = await self.today_row()
        self.assertEqual(day.average_temperature_celsius, 25.0)

    async def test_a_reading_with_no_humidity_leaves_the_humidity_it_already_had(self):
        await self.record(build_report(11.0, humidity=70.0), build_report(12.0, humidity=None))

        day = await self.today_row()
        self.assertEqual(day.reading_count, 2)
        self.assertEqual(day.minimum_humidity_percent, 70.0)
        self.assertEqual(day.average_humidity_percent, 70.0)
        self.assertEqual(day.maximum_temperature_celsius, 12.0)

    async def test_yesterdays_row_is_left_alone(self):
        async with self.uow_factory() as uow:
            await uow.outdoor_weather_days.save_day(
                self.household_calendar.local_date(FROZEN_NOW - timedelta(days=1)),
                {"reading_count": 24, "minimum_temperature_celsius": 3.0},
            )

        await self.record(build_report(11.0))

        async with self.uow_factory() as uow:
            yesterday = await uow.outdoor_weather_days.retrieve_day(
                self.household_calendar.local_date(FROZEN_NOW - timedelta(days=1))
            )
        self.assertEqual(yesterday.reading_count, 24)
        self.assertEqual(yesterday.minimum_temperature_celsius, 3.0)
