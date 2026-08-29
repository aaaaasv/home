import unittest
from datetime import datetime, timezone

from src.common.config import Settings
from src.modules.power.domain import EcoFlowState
from src.modules.room_climate.domain import RoomClimate
from src.mqtt.power import register_listeners as register_power_listeners
from src.mqtt.room_climate import register_listeners as register_climate_listeners
from src.mqtt.surface import MqttContext, MqttSurface
from src.tests.integration.test_air_conditioner_mqtt import PREFIX, FakeBroker


class RecordingEcoFlowStation:
    def __init__(self, state: EcoFlowState | None):
        self.state = state
        self.refresh_calls: list[bool] = []

    async def read_state(self, refresh: bool = False) -> EcoFlowState | None:
        self.refresh_calls.append(refresh)
        return self.state


class RecordingRoomClimateSensor:
    def __init__(self, climate: RoomClimate | None):
        self.climate = climate

    async def read(self) -> RoomClimate | None:
        return self.climate


def build_ecoflow_state(**overrides) -> EcoFlowState:
    defaults = dict(
        battery_percent=82.4,
        on_mains=True,
        ac_input_power=310,
        ac_output_power=90,
        ac_output_on=True,
        usb_output_on=False,
        dc_output_on=False,
        remaining_minutes=120,
        charge_limit_max=80,
        backup_reserve_percent=None,
        cell_temperature_celsius=27,
        as_of=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return EcoFlowState(**defaults)


def build_settings(**overrides) -> Settings:
    defaults = dict(
        TELEGRAM_BOT_TOKEN="123:abc",
        ECOFLOW_ENABLED=True,
        CLIMATE_SENSOR_ENABLED=True,
        MQTT_PUBLISH_INTERVAL_SECONDS=3600,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def build_power_surface(broker: FakeBroker, station, settings: Settings) -> MqttSurface:
    surface = MqttSurface(host="broker", port=1883, topic_prefix=PREFIX, client_factory=lambda _: broker)
    register_power_listeners(surface, MqttContext(settings=settings, ecoflow_station=station))
    return surface


def build_climate_surface(broker: FakeBroker, sensor, settings: Settings) -> MqttSurface:
    surface = MqttSurface(host="broker", port=1883, topic_prefix=PREFIX, client_factory=lambda _: broker)
    register_climate_listeners(surface, MqttContext(settings=settings, room_climate_sensor=sensor))
    return surface


class PublishPowerStateTestCase(unittest.IsolatedAsyncioTestCase):
    """
    The grid as a contact sensor, because no phone has a tile that means "світло є".

    the station's own charge rides on the same accessory: during an outage nobody asks one question without
    the other.
    """

    async def test_publishing_a_station_on_mains_reports_the_grid_up_and_charging(self):
        broker = FakeBroker()
        surface = build_power_surface(broker, RecordingEcoFlowStation(build_ecoflow_state()), build_settings())

        await surface.serve_one_connection()

        self.assertEqual(
            broker.last_published(),
            {
                f"{PREFIX}/power/available": "true",
                f"{PREFIX}/power/mains": "true",
                f"{PREFIX}/power/battery": "82",
                f"{PREFIX}/power/battery-low": "false",
                f"{PREFIX}/power/charging": "true",
            },
        )

    async def test_publishing_a_station_off_mains_reports_the_grid_down_and_not_charging(self):
        broker = FakeBroker()
        state = build_ecoflow_state(on_mains=False, ac_input_power=0)
        surface = build_power_surface(broker, RecordingEcoFlowStation(state), build_settings())

        await surface.serve_one_connection()

        self.assertEqual(broker.last_published()[f"{PREFIX}/power/mains"], "false")
        self.assertEqual(broker.last_published()[f"{PREFIX}/power/charging"], "false")

    async def test_a_low_battery_while_on_mains_is_not_reported_as_low(self):
        broker = FakeBroker()
        state = build_ecoflow_state(battery_percent=12.0, on_mains=True)
        surface = build_power_surface(broker, RecordingEcoFlowStation(state), build_settings())

        await surface.serve_one_connection()

        self.assertEqual(broker.last_published()[f"{PREFIX}/power/battery-low"], "false")

    async def test_a_low_battery_while_the_grid_is_down_is_reported_as_low(self):
        broker = FakeBroker()
        state = build_ecoflow_state(battery_percent=12.0, on_mains=False, ac_input_power=0)
        surface = build_power_surface(broker, RecordingEcoFlowStation(state), build_settings())

        await surface.serve_one_connection()

        self.assertEqual(broker.last_published()[f"{PREFIX}/power/battery-low"], "true")

    async def test_publishing_an_unreachable_station_says_nothing_about_the_grid(self):
        broker = FakeBroker()
        surface = build_power_surface(broker, RecordingEcoFlowStation(None), build_settings())

        await surface.serve_one_connection()

        self.assertEqual(broker.last_published(), {f"{PREFIX}/power/available": "false"})

    async def test_publishing_reads_the_cached_state_rather_than_waking_the_radio(self):
        broker = FakeBroker()
        station = RecordingEcoFlowStation(build_ecoflow_state())
        surface = build_power_surface(broker, station, build_settings())

        await surface.serve_one_connection()

        self.assertEqual(station.refresh_calls, [False])

    async def test_a_flat_without_a_station_publishes_nothing(self):
        broker = FakeBroker()
        settings = build_settings(ECOFLOW_ENABLED=False)
        surface = build_power_surface(broker, RecordingEcoFlowStation(build_ecoflow_state()), settings)

        await surface.serve_one_connection()

        self.assertEqual(broker.published, [])


class PublishRoomClimateTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_publishing_the_air_rounds_it_to_what_a_tile_shows(self):
        broker = FakeBroker()
        climate = RoomClimate(temperature_celsius=26.34, relative_humidity_percent=41.72)
        surface = build_climate_surface(broker, RecordingRoomClimateSensor(climate), build_settings())

        await surface.serve_one_connection()

        self.assertEqual(
            broker.last_published(),
            {
                f"{PREFIX}/room-climate/available": "true",
                f"{PREFIX}/room-climate/temperature": "26.3",
                f"{PREFIX}/room-climate/humidity": "42",
            },
        )

    async def test_publishing_an_unreadable_sensor_goes_quiet_rather_than_leaving_the_last_number(self):
        broker = FakeBroker()
        surface = build_climate_surface(broker, RecordingRoomClimateSensor(None), build_settings())

        await surface.serve_one_connection()

        self.assertEqual(broker.last_published(), {f"{PREFIX}/room-climate/available": "false"})

    async def test_a_flat_without_a_sensor_publishes_nothing(self):
        broker = FakeBroker()
        settings = build_settings(CLIMATE_SENSOR_ENABLED=False)
        climate = RoomClimate(temperature_celsius=26.0, relative_humidity_percent=40.0)
        surface = build_climate_surface(broker, RecordingRoomClimateSensor(climate), settings)

        await surface.serve_one_connection()

        self.assertEqual(broker.published, [])
