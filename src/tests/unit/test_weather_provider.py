import unittest
from datetime import timedelta

from src.common.time import current_time
from src.modules.weather.domain import PollenSpecies
from src.modules.weather.services.weather_provider import (
    WEATHER_RECENT_MAX_AGE_SECONDS,
    OpenMeteoWeatherProvider,
    parse_weather_report,
    resolve_peak_wind_speed,
    resolve_rain_outlook,
)

# a real kyiv day: the 90% peak falls at 02:00, long before the 08:00 digest goes out
KYIV_HOURLY_PROBABILITIES = [33, 60, 90, 70, 30, 28, 18, 45, 63, 43, 13, 8, 20, 15, 10, 23, 35, 40, 13, 3, 0, 0, 0, 0]


def build_hourly(
    probabilities: list[int | None],
    wind_speeds: list[float | None] | None = None,
    temperatures: list[float | None] | None = None,
    weather_codes: list[int | None] | None = None,
) -> dict:
    count = len(probabilities)
    return {
        "time": [f"2026-07-20T{hour:02d}:00" for hour in range(count)],
        "precipitation_probability": probabilities,
        "wind_speed_10m": wind_speeds if wind_speeds is not None else [1.0] * count,
        "temperature_2m": temperatures if temperatures is not None else [20.0 + hour for hour in range(count)],
        "weather_code": weather_codes if weather_codes is not None else [1] * count,
    }


class ParseWeatherReportTestCase(unittest.TestCase):
    def build_payloads(self) -> tuple[dict, dict]:
        forecast = {
            "current": {"temperature_2m": 28.3, "apparent_temperature": 31.9, "relative_humidity_2m": 55},
            "daily": {"uv_index_max": [6.35]},
            "hourly": build_hourly(KYIV_HOURLY_PROBABILITIES),
        }
        air_quality = {
            "current": {"european_aqi": 39.4, "pm2_5": 8.8},
            "hourly": {
                "ragweed_pollen": [0.0, 0.0],
                "grass_pollen": [4.5, 10.9],
                "birch_pollen": [None, 0.0],
                "alder_pollen": [0.0],
                "mugwort_pollen": [1.4, 4.2],
            },
        }
        return forecast, air_quality

    def test_parse_weather_report_reads_temperature_rain_and_air_quality(self):
        forecast, air_quality = self.build_payloads()

        report = parse_weather_report(forecast, air_quality, current_hour=8)

        self.assertEqual(report.temperature_celsius, 28.3)
        self.assertEqual(report.apparent_temperature_celsius, 31.9)
        self.assertEqual(report.relative_humidity_percent, 55)
        self.assertEqual(report.uv_index_max, 6.35)
        self.assertEqual(report.precipitation_probability_percent, 63)
        self.assertEqual(report.european_air_quality_index, 39)
        self.assertEqual(report.pm2_5_micrograms, 8.8)

    def test_parse_weather_report_takes_the_daily_peak_of_each_pollen_species(self):
        forecast, air_quality = self.build_payloads()

        report = parse_weather_report(forecast, air_quality, current_hour=8)

        peaks = {reading.species: reading.grains_per_cubic_meter for reading in report.pollen}
        self.assertEqual(
            peaks,
            {
                PollenSpecies.RAGWEED: 0.0,
                PollenSpecies.GRASS: 10.9,
                PollenSpecies.BIRCH: 0.0,
                PollenSpecies.ALDER: 0.0,
                PollenSpecies.MUGWORT: 4.2,
            },
        )

    def test_parse_weather_report_without_pollen_returns_no_readings(self):
        forecast, air_quality = self.build_payloads()
        air_quality["hourly"] = {}

        report = parse_weather_report(forecast, air_quality, current_hour=8)

        self.assertEqual(report.pollen, [])

    def test_parse_weather_report_without_air_quality_leaves_those_fields_none(self):
        forecast, _ = self.build_payloads()

        report = parse_weather_report(forecast, {}, current_hour=8)

        self.assertIsNone(report.european_air_quality_index)
        self.assertIsNone(report.pm2_5_micrograms)
        self.assertEqual(report.pollen, [])


class ResolvePeakWindSpeedTestCase(unittest.TestCase):
    def test_resolve_peak_wind_speed_ignores_hours_already_past(self):
        hourly = build_hourly([0, 0, 0, 0], wind_speeds=[19.0, 3.0, 4.0, 6.0])

        self.assertEqual(resolve_peak_wind_speed(hourly, current_hour=1), 6.0)

    def test_resolve_peak_wind_speed_takes_the_strongest_hour_still_ahead(self):
        hourly = build_hourly([0, 0, 0, 0], wind_speeds=[1.0, 3.0, 12.5, 6.0])

        self.assertEqual(resolve_peak_wind_speed(hourly, current_hour=0), 12.5)

    def test_resolve_peak_wind_speed_past_the_last_forecast_hour_returns_nothing(self):
        hourly = build_hourly([0, 0], wind_speeds=[4.0, 5.0])

        self.assertIsNone(resolve_peak_wind_speed(hourly, current_hour=5))

    def test_resolve_peak_wind_speed_without_hourly_data_returns_nothing(self):
        self.assertIsNone(resolve_peak_wind_speed({}, current_hour=8))


class ResolveRainOutlookTestCase(unittest.TestCase):
    def test_resolve_rain_outlook_at_the_morning_digest_ignores_the_overnight_peak(self):
        probability, window = resolve_rain_outlook(build_hourly(KYIV_HOURLY_PROBABILITIES), current_hour=8)

        self.assertEqual(probability, 63)
        self.assertEqual((window.start_hour, window.end_hour), (8, 9))

    def test_resolve_rain_outlook_at_midnight_spans_the_overnight_peak(self):
        probability, window = resolve_rain_outlook(build_hourly(KYIV_HOURLY_PROBABILITIES), current_hour=0)

        self.assertEqual(probability, 90)
        self.assertEqual((window.start_hour, window.end_hour), (1, 3))

    def test_resolve_rain_outlook_with_an_isolated_peak_returns_a_single_hour(self):
        probability, window = resolve_rain_outlook(build_hourly([0, 0, 80, 0, 0]), current_hour=0)

        self.assertEqual(probability, 80)
        self.assertEqual((window.start_hour, window.end_hour), (2, 2))

    def test_resolve_rain_outlook_on_a_dry_day_returns_no_window(self):
        probability, window = resolve_rain_outlook(build_hourly([0, 0, 0, 0]), current_hour=0)

        self.assertEqual(probability, 0)
        self.assertIsNone(window)

    def test_resolve_rain_outlook_skips_hours_with_no_reading(self):
        probability, window = resolve_rain_outlook(build_hourly([90, None, 40, 20]), current_hour=1)

        self.assertEqual(probability, 40)
        self.assertEqual((window.start_hour, window.end_hour), (2, 3))

    def test_resolve_rain_outlook_past_the_last_forecast_hour_returns_nothing(self):
        probability, window = resolve_rain_outlook(build_hourly([10, 20]), current_hour=5)

        self.assertIsNone(probability)
        self.assertIsNone(window)

    def test_resolve_rain_outlook_without_hourly_data_returns_nothing(self):
        probability, window = resolve_rain_outlook({}, current_hour=8)

        self.assertIsNone(probability)
        self.assertIsNone(window)


class RecentWeatherCacheTestCase(unittest.TestCase):
    def build_provider(self) -> OpenMeteoWeatherProvider:
        return OpenMeteoWeatherProvider(latitude=50.45, longitude=30.52, timezone_name="Europe/Kyiv")

    def test_recent_before_any_fetch_returns_nothing(self):
        provider = self.build_provider()

        self.assertIsNone(provider.recent())

    def test_recent_returns_the_cached_report_while_it_is_fresh(self):
        provider = self.build_provider()
        cached = object()
        provider._cached_report = cached
        provider._cached_at = current_time() - timedelta(seconds=WEATHER_RECENT_MAX_AGE_SECONDS - 60)

        self.assertIs(provider.recent(), cached)

    def test_recent_returns_nothing_once_the_cache_is_older_than_the_window(self):
        provider = self.build_provider()
        provider._cached_report = object()
        provider._cached_at = current_time() - timedelta(seconds=WEATHER_RECENT_MAX_AGE_SECONDS + 60)

        self.assertIsNone(provider.recent())
