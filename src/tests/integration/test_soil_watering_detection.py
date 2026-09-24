import json
import unittest

from src.common.config import Settings
from src.mqtt.plant_soil import register_listeners as register_soil_listeners
from src.mqtt.surface import MqttContext, MqttSurface
from src.tests.integration.test_air_conditioner_mqtt import PREFIX, FakeBroker

SENSOR_TOPIC = "zigbee2mqtt/soil-peperoni"


def build_settings(**overrides) -> Settings:
    defaults = dict(
        TELEGRAM_BOT_TOKEN="123:abc",
        PLANT_SOIL_SENSORS=json.dumps({"soil-peperoni": 2}),
        MQTT_PUBLISH_INTERVAL_SECONDS=3600,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def reading(soil_moisture: float) -> bytes:
    return json.dumps({"soil_moisture": soil_moisture, "temperature": 24.0, "humidity": 55}).encode()


class SoilWateringDetectionTestCase(unittest.IsolatedAsyncioTestCase):
    """
    A pour is a step, not a level: the probe reads single digits for days and tens of points minutes later.

    the cost of being wrong is asymmetric and that is what sets the thresholds — a missed watering is a hole
    in the record, an invented one is a plant the schedule thinks is watered when it is dry.
    """

    def setUp(self):
        self.watered: list[int] = []

    async def record(self, plant_id: int) -> None:
        self.watered.append(plant_id)

    def build_surface(self, broker: FakeBroker, settings: Settings | None = None) -> MqttSurface:
        surface = MqttSurface(host="broker", port=1883, topic_prefix=PREFIX, client_factory=lambda _: broker)
        register_soil_listeners(
            surface, MqttContext(settings=settings or build_settings(), record_watering=self.record)
        )
        return surface

    async def test_a_jump_from_dry_to_wet_records_the_watering(self):
        broker = FakeBroker([(SENSOR_TOPIC, reading(2)), (SENSOR_TOPIC, reading(46))])

        await self.build_surface(broker).serve_one_connection()

        self.assertEqual(self.watered, [2])

    async def test_the_first_reading_alone_records_nothing(self):
        broker = FakeBroker([(SENSOR_TOPIC, reading(46))])

        await self.build_surface(broker).serve_one_connection()

        self.assertEqual(self.watered, [])

    async def test_soil_slowly_drying_records_nothing(self):
        broker = FakeBroker([(SENSOR_TOPIC, reading(40)), (SENSOR_TOPIC, reading(37)), (SENSOR_TOPIC, reading(34))])

        await self.build_surface(broker).serve_one_connection()

        self.assertEqual(self.watered, [])

    async def test_a_twitch_in_bone_dry_soil_is_not_a_watering(self):
        broker = FakeBroker([(SENSOR_TOPIC, reading(0)), (SENSOR_TOPIC, reading(12))])

        await self.build_surface(broker).serve_one_connection()

        self.assertEqual(self.watered, [])

    async def test_a_small_rise_in_wet_soil_is_not_a_watering(self):
        broker = FakeBroker([(SENSOR_TOPIC, reading(40)), (SENSOR_TOPIC, reading(46))])

        await self.build_surface(broker).serve_one_connection()

        self.assertEqual(self.watered, [])

    async def test_one_pour_is_recorded_once_even_while_the_soil_keeps_soaking(self):
        broker = FakeBroker([(SENSOR_TOPIC, reading(3)), (SENSOR_TOPIC, reading(45)), (SENSOR_TOPIC, reading(52))])

        await self.build_surface(broker).serve_one_connection()

        self.assertEqual(self.watered, [2])

    async def test_an_unreadable_payload_is_ignored(self):
        broker = FakeBroker([(SENSOR_TOPIC, reading(2)), (SENSOR_TOPIC, b"not json"), (SENSOR_TOPIC, reading(46))])

        await self.build_surface(broker).serve_one_connection()

        self.assertEqual(self.watered, [2])

    async def test_a_probe_with_no_plant_behind_it_is_not_followed(self):
        broker = FakeBroker([(SENSOR_TOPIC, reading(2)), (SENSOR_TOPIC, reading(46))])
        surface = self.build_surface(broker, build_settings(PLANT_SOIL_SENSORS=""))

        await surface.serve_one_connection()

        self.assertEqual(self.watered, [])
        self.assertEqual(broker.subscriptions, [])
