import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.bot.handlers.weather.formatting import render_climate_digest
from src.infrastructure.adapters.sensor_community_air_quality import SensorCommunityAirQuality
from src.modules.weather.domain import LocalAirQuality, WeatherReport


class StubSensorHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — the name is BaseHTTPRequestHandler's
        body = json.dumps(self.server.rows).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        pass


def sample(sensor_id: int, pm2_5, timestamp: str = "2026-09-11 19:57:43") -> dict:
    return {
        "sensor": {"id": sensor_id},
        "timestamp": timestamp,
        "sensordatavalues": [
            {"value_type": "P1", "value": "6.43"},
            {"value_type": "P2", "value": pm2_5},
        ],
    }


class SensorCommunityAirQualityTestCase(unittest.IsolatedAsyncioTestCase):
    """
    Volunteer sensors are the only real measurement near this flat, and also the least reliable source in it.

    they go offline without notice, over-read badly in high humidity, and one of them being wrong is ordinary.
    so every way the network can mislead has to end in either a median across several or nothing at all.
    """

    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), StubSensorHandler)
        self.server.rows = []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.source = SensorCommunityAirQuality(latitude=50.44, longitude=30.46, radius_km=2, timeout_seconds=2.0)
        self.source.url = f"http://127.0.0.1:{self.server.server_port}/"

    async def test_read_with_several_sensors_returns_their_median(self):
        self.server.rows = [sample(1, "2.0"), sample(2, "4.0"), sample(3, "9.0")]

        reading = await self.source.read()

        self.assertEqual((reading.pm2_5_micrograms, reading.sensor_count), (4.0, 3))

    async def test_read_takes_only_the_newest_row_from_each_sensor(self):
        self.server.rows = [
            sample(1, "100.0", timestamp="2026-09-11 19:00:00"),
            sample(1, "3.0", timestamp="2026-09-11 19:57:43"),
        ]

        reading = await self.source.read()

        self.assertEqual((reading.pm2_5_micrograms, reading.sensor_count), (3.0, 1))

    async def test_read_ignores_an_unplugged_sensor_reporting_an_absurd_value(self):
        self.server.rows = [sample(1, "3.0"), sample(2, "999999")]

        reading = await self.source.read()

        self.assertEqual((reading.pm2_5_micrograms, reading.sensor_count), (3.0, 1))

    async def test_read_with_nobody_answering_returns_nothing_so_the_model_stands_in(self):
        self.server.rows = []

        reading = await self.source.read()

        self.assertIsNone(reading)

    async def test_read_with_the_network_unreachable_returns_nothing(self):
        self.server.shutdown()
        self.server.server_close()

        reading = await self.source.read()

        self.assertIsNone(reading)


def build_report(**overrides) -> WeatherReport:
    defaults = dict(
        temperature_celsius=18.0,
        apparent_temperature_celsius=18.0,
        relative_humidity_percent=55.0,
        temperature_max_celsius=21.0,
        temperature_min_celsius=12.0,
        temperature_evening_celsius=None,
        uv_index_max=None,
        is_thunderstorm_expected=False,
        wind_speed_meters_per_second=3.2,
        precipitation_probability_percent=10,
        rain_window=None,
        european_air_quality_index=39,
        pm2_5_micrograms=8.8,
        pollen=[],
    )
    defaults.update(overrides)
    return WeatherReport(**defaults)


class DigestAirQualityLineTestCase(unittest.TestCase):
    """
    The line was always there; what changes is whether it states a measurement or a model.

    the modelled index covers ~11 km and averages away exactly the local spikes worth knowing about — on
    08.09.2026 the sensors near this flat saw an hour at 29.6 µg/m³ while the model saw an ordinary day.
    """

    def test_render_prefers_the_measured_value_over_the_modelled_index(self):
        outdoor = build_report(european_air_quality_index=39, pm2_5_micrograms=8.8)

        text = render_climate_digest(None, outdoor, local_air=LocalAirQuality(pm2_5_micrograms=2.4, sensor_count=3))

        self.assertIn("🌫 повітря: чудове · PM2.5 2.4 мкг/м³", text)
        self.assertNotIn("AQI", text)

    def test_render_falls_back_to_the_modelled_index_when_no_sensor_answers(self):
        outdoor = build_report(european_air_quality_index=39, pm2_5_micrograms=8.8)

        text = render_climate_digest(None, outdoor, local_air=None)

        self.assertIn("🌫 повітря: добре (AQI 39)", text)

    def test_render_names_the_band_from_the_measured_value_not_the_index(self):
        outdoor = build_report(european_air_quality_index=10, pm2_5_micrograms=1.0)

        text = render_climate_digest(None, outdoor, local_air=LocalAirQuality(pm2_5_micrograms=29.6, sensor_count=2))

        self.assertIn("🌫 повітря: погане · PM2.5 29.6 мкг/м³", text)

    def test_render_drops_a_trailing_zero_so_a_clean_day_reads_as_a_whole_number(self):
        outdoor = build_report(european_air_quality_index=10, pm2_5_micrograms=1.0)

        text = render_climate_digest(None, outdoor, local_air=LocalAirQuality(pm2_5_micrograms=3.0, sensor_count=1))

        self.assertIn("PM2.5 3 мкг/м³", text)
