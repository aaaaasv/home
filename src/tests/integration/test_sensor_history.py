import json
from datetime import timedelta

from src.common.config import Settings
from src.infrastructure.db.models import SensorDay, SensorReading
from src.modules.sensors.commands import RecordSensorReadingCommand
from src.modules.sensors.use_cases.fold_sensor_days import FoldSensorDaysUseCase
from src.modules.sensors.use_cases.record_sensor_reading import RecordSensorReadingUseCase
from src.mqtt.home_sensors import register_listeners as register_sensor_listeners
from src.mqtt.plant_soil import register_listeners as register_soil_listeners
from src.mqtt.surface import MqttContext, MqttSurface
from src.tests.integration.base import BaseIntegrationTestCase
from src.tests.integration.test_air_conditioner_mqtt import PREFIX, FakeBroker

BEDROOM_TOPIC = "zigbee2mqtt/temp-bedroom"
PROBE_TOPIC = "zigbee2mqtt/soil-peperoni"

SENSOR_ROOMS = json.dumps({"temp-bedroom": "спальня", "temp-hall": "коридор"})


def build_settings(**overrides) -> Settings:
    defaults = dict(
        TELEGRAM_BOT_TOKEN="123:abc",
        SENSOR_ROOMS=SENSOR_ROOMS,
        PLANT_SOIL_SENSORS=json.dumps({"soil-peperoni": 2}),
        MQTT_PUBLISH_INTERVAL_SECONDS=3600,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def air(temperature: float, humidity: float, battery: int = 100) -> bytes:
    return json.dumps(
        {"temperature": temperature, "humidity": humidity, "battery": battery, "linkquality": 120}
    ).encode()


def soil(moisture: float) -> bytes:
    return json.dumps({"soil_moisture": moisture, "temperature": 22.0, "humidity": 60, "battery": 100}).encode()


class RecordSensorReadingTestCase(BaseIntegrationTestCase):
    """
    The bot's memory of what the house measured — the hole that made last night's experiment a hand-kept file.

    the sensors report on change, so a reading is not a poll result but an event, and the only timestamp worth
    trusting is the moment it arrived.
    """

    async def record(self, **overrides) -> None:
        defaults = dict(sensor="temp-bedroom", room="спальня", temperature_celsius=22.9)
        defaults.update(overrides)
        await RecordSensorReadingUseCase(uow=self.uow, household_calendar=self.household_calendar)(
            RecordSensorReadingCommand(**defaults)
        )

    async def list_readings(self) -> list[SensorReading]:
        async with self.uow as uow:
            return await uow.sensor_readings.list_measured_between(
                "temp-bedroom", self.household_calendar.now() - timedelta(days=1), self.household_calendar.now()
            )

    async def test_record_sensor_reading_stores_it_stamped_with_the_household_clock(self):
        await self.record(relative_humidity_percent=53.7, battery_percent=100)

        async with self.uow as uow:
            reading = await uow.sensor_readings.retrieve_latest("temp-bedroom")

        self.assertEqual(reading.sensor, "temp-bedroom")
        self.assertEqual(reading.room, "спальня")
        self.assertEqual(reading.temperature_celsius, 22.9)
        self.assertEqual(reading.relative_humidity_percent, 53.7)
        self.assertEqual(reading.battery_percent, 100)
        self.assertEqual(reading.soil_moisture_percent, None)
        self.assertEqual(reading.measured_at, self.household_calendar.now())

    async def test_record_sensor_reading_carrying_no_measurement_stores_nothing(self):
        await self.record(temperature_celsius=None)

        async with self.uow as uow:
            reading = await uow.sensor_readings.retrieve_latest("temp-bedroom")

        self.assertEqual(reading, None)

    async def test_record_sensor_reading_for_a_probe_keeps_the_room_empty(self):
        await RecordSensorReadingUseCase(uow=self.uow, household_calendar=self.household_calendar)(
            RecordSensorReadingCommand(sensor="soil-peperoni", soil_moisture_percent=46.0, temperature_celsius=22.1)
        )

        async with self.uow as uow:
            reading = await uow.sensor_readings.retrieve_latest("soil-peperoni")

        self.assertEqual(reading.room, None)
        self.assertEqual(reading.soil_moisture_percent, 46.0)


class FoldSensorDaysTestCase(BaseIntegrationTestCase):
    """
    A year of six sensors has to be two thousand rows, not two million, and the fold is what makes that true.

    it must also be safe to run at any hour: a rewrite of the same day, twice, is the same day.
    """

    async def seed_reading(self, sensor: str, measured_at, **values) -> None:
        async with self.uow as uow:
            uow.session.add(SensorReading(sensor=sensor, measured_at=measured_at, **values))

    async def fold(self, raw_retention_days: int = 7) -> int:
        return await FoldSensorDaysUseCase(
            uow=self.uow, household_calendar=self.household_calendar, raw_retention_days=raw_retention_days
        )()

    async def list_days(self, sensor: str) -> list[SensorDay]:
        async with self.uow as uow:
            return await uow.sensor_days.list_between(sensor, self.today - timedelta(days=3), self.today)

    async def test_fold_sensor_days_writes_one_row_per_sensor_with_the_day_extremes(self):
        moment = self.household_calendar.now()
        await self.seed_reading("temp-hall", moment - timedelta(hours=3), room="коридор", temperature_celsius=23.9)
        await self.seed_reading("temp-hall", moment - timedelta(hours=2), room="коридор", temperature_celsius=23.0)
        await self.seed_reading("temp-hall", moment - timedelta(hours=1), room="коридор", temperature_celsius=23.4)

        folded = await self.fold()

        days = await self.list_days("temp-hall")
        self.assertEqual(folded, 1)
        self.assertEqual(len(days), 1)
        self.assertEqual(days[0].day, self.today)
        self.assertEqual(days[0].room, "коридор")
        self.assertEqual(days[0].reading_count, 3)
        self.assertEqual(days[0].minimum_temperature_celsius, 23.0)
        self.assertEqual(days[0].maximum_temperature_celsius, 23.9)
        self.assertEqual(days[0].average_temperature_celsius, 23.433333333333334)

    async def test_fold_sensor_days_leaves_a_dimension_empty_when_the_sensor_never_reports_it(self):
        await self.seed_reading(
            "soil-peperoni", self.household_calendar.now() - timedelta(hours=1), soil_moisture_percent=12.0
        )

        await self.fold()

        days = await self.list_days("soil-peperoni")
        self.assertEqual(days[0].minimum_soil_moisture_percent, 12.0)
        self.assertEqual(days[0].average_temperature_celsius, None)
        self.assertEqual(days[0].minimum_humidity_percent, None)

    async def test_fold_sensor_days_run_twice_rewrites_the_same_day_rather_than_adding_one(self):
        moment = self.household_calendar.now()
        await self.seed_reading("temp-hall", moment - timedelta(hours=2), room="коридор", temperature_celsius=23.9)
        await self.fold()
        await self.seed_reading("temp-hall", moment - timedelta(hours=1), room="коридор", temperature_celsius=21.0)

        await self.fold()

        days = await self.list_days("temp-hall")
        self.assertEqual(len(days), 1)
        self.assertEqual(days[0].reading_count, 2)
        self.assertEqual(days[0].minimum_temperature_celsius, 21.0)

    async def test_fold_sensor_days_prunes_raw_readings_past_the_retention_window(self):
        moment = self.household_calendar.now()
        await self.seed_reading("temp-hall", moment - timedelta(days=9), room="коридор", temperature_celsius=19.0)
        await self.seed_reading("temp-hall", moment - timedelta(hours=1), room="коридор", temperature_celsius=23.0)

        await self.fold(raw_retention_days=7)

        async with self.uow as uow:
            remaining = await uow.sensor_readings.list_measured_between(
                "temp-hall", moment - timedelta(days=30), moment
            )
        self.assertEqual([reading.temperature_celsius for reading in remaining], [23.0])

    async def test_fold_sensor_days_keeps_yesterdays_summary_after_the_day_has_ended(self):
        yesterday = self.today - timedelta(days=1)
        await self.seed_reading(
            "temp-hall", self.household_calendar.start_of_day(yesterday) + timedelta(hours=10), temperature_celsius=20.0
        )

        await self.fold()

        days = await self.list_days("temp-hall")
        self.assertEqual([day.day for day in days], [yesterday])
        self.assertEqual(days[0].average_temperature_celsius, 20.0)


class SensorListenerTestCase(BaseIntegrationTestCase):
    """The path from the broker to the table, including the one topic two modules both care about."""

    def build_surface(self, broker: FakeBroker, settings: Settings | None = None) -> MqttSurface:
        settings = settings or build_settings()
        surface = MqttSurface(host="broker", port=1883, topic_prefix=PREFIX, client_factory=lambda _: broker)
        self.watered: list[int] = []

        async def record_watering(plant_id: int) -> None:
            self.watered.append(plant_id)

        async def record_sensor_reading(data: RecordSensorReadingCommand) -> None:
            await RecordSensorReadingUseCase(uow=self.uow, household_calendar=self.household_calendar)(data)

        context = MqttContext(
            settings=settings, record_watering=record_watering, record_sensor_reading=record_sensor_reading
        )
        register_sensor_listeners(surface, context)
        register_soil_listeners(surface, context)
        return surface

    async def test_a_room_sensor_message_is_written_down_with_its_room(self):
        broker = FakeBroker([(BEDROOM_TOPIC, air(22.9, 53.7))])

        await self.build_surface(broker).serve_one_connection()

        async with self.uow as uow:
            reading = await uow.sensor_readings.retrieve_latest("temp-bedroom")
        self.assertEqual(reading.room, "спальня")
        self.assertEqual(reading.temperature_celsius, 22.9)
        self.assertEqual(reading.relative_humidity_percent, 53.7)

    async def test_a_sensor_named_by_no_setting_is_not_followed(self):
        broker = FakeBroker([("zigbee2mqtt/temp-bathroom", air(23.7, 52.1))])

        await self.build_surface(broker).serve_one_connection()

        async with self.uow as uow:
            reading = await uow.sensor_readings.retrieve_latest("temp-bathroom")
        self.assertEqual(reading, None)
        self.assertNotIn("zigbee2mqtt/temp-bathroom", broker.subscriptions)

    async def test_a_probe_reading_is_both_written_down_and_watched_for_a_watering(self):
        broker = FakeBroker([(PROBE_TOPIC, soil(2)), (PROBE_TOPIC, soil(46))])

        await self.build_surface(broker).serve_one_connection()

        async with self.uow as uow:
            readings = await uow.sensor_readings.list_measured_between(
                "soil-peperoni",
                self.household_calendar.now() - timedelta(days=1),
                self.household_calendar.now() + timedelta(days=1),
            )
        self.assertEqual([reading.soil_moisture_percent for reading in readings], [2.0, 46.0])
        self.assertEqual(self.watered, [2])

    async def test_an_unreadable_payload_leaves_the_history_untouched(self):
        broker = FakeBroker([(BEDROOM_TOPIC, b"not json"), (BEDROOM_TOPIC, air(22.9, 53.7))])

        await self.build_surface(broker).serve_one_connection()

        async with self.uow as uow:
            reading = await uow.sensor_readings.retrieve_latest("temp-bedroom")
        self.assertEqual(reading.temperature_celsius, 22.9)

    async def test_the_bot_subscribes_to_every_configured_sensor_once(self):
        broker = FakeBroker([])

        await self.build_surface(broker).serve_one_connection()

        self.assertEqual(
            sorted(broker.subscriptions),
            ["zigbee2mqtt/soil-peperoni", "zigbee2mqtt/temp-bedroom", "zigbee2mqtt/temp-hall"],
        )
