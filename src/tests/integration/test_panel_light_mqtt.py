import json
import tempfile
import unittest
from pathlib import Path

from src.common.config import Settings
from src.infrastructure.adapters.file_panel_light import FilePanelLight
from src.mqtt.panel_light import SET_BRIGHTNESS, SET_ON, TAP_BRIGHTNESS_PERCENT
from src.mqtt.panel_light import register_listeners as register_panel_light_listeners
from src.mqtt.surface import MqttContext, MqttSurface
from src.tests.integration.test_air_conditioner_mqtt import PREFIX, FakeBroker


def build_settings(**overrides) -> Settings:
    defaults = dict(
        TELEGRAM_BOT_TOKEN="123:abc",
        PANEL_LIGHT_ENABLED=True,
        MQTT_PUBLISH_INTERVAL_SECONDS=3600,
    )
    defaults.update(overrides)
    return Settings(**defaults)


class PanelLightMqttTestCase(unittest.IsolatedAsyncioTestCase):
    """
    The switchboard strip as a lamp on the broker.

    the automatic half of this light lives on the host and never asks the bot: what is tested here is only
    the hand on it, and the one thing that must never happen — a lamp tile showing a level while the host
    service that owns the pin is not answering at all.
    """

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.directory.name) / "state.json"
        self.command_path = Path(self.directory.name) / "command.json"
        self.panel_light = FilePanelLight(state_path=self.state_path, command_path=self.command_path)

    def tearDown(self):
        self.directory.cleanup()

    def write_state(self, on: bool, percent: float) -> None:
        self.state_path.write_text(json.dumps({"on": on, "percent": percent}))

    def build_surface(self, broker: FakeBroker, settings: Settings | None = None) -> MqttSurface:
        surface = MqttSurface(host="broker", port=1883, topic_prefix=PREFIX, client_factory=lambda _: broker)
        register_panel_light_listeners(
            surface, MqttContext(settings=settings or build_settings(), panel_light=self.panel_light)
        )
        return surface

    async def test_publishing_a_lit_strip_reports_it_on_with_its_level(self):
        self.write_state(on=True, percent=20.0)
        broker = FakeBroker()
        surface = self.build_surface(broker)

        await surface.serve_one_connection()

        self.assertEqual(
            broker.last_published(),
            {
                f"{PREFIX}/panel-light/available": "true",
                f"{PREFIX}/panel-light/on": "true",
                f"{PREFIX}/panel-light/brightness": "20",
            },
        )

    async def test_publishing_without_the_host_service_reports_the_lamp_unavailable(self):
        broker = FakeBroker()
        surface = self.build_surface(broker)

        await surface.serve_one_connection()

        self.assertEqual(broker.last_published(), {f"{PREFIX}/panel-light/available": "false"})

    async def test_tapping_the_tile_on_asks_the_host_for_the_walking_level(self):
        self.write_state(on=False, percent=0.0)
        broker = FakeBroker([(f"{PREFIX}/{SET_ON}", b"true")])
        surface = self.build_surface(broker)

        await surface.serve_one_connection()

        self.assertEqual(json.loads(self.command_path.read_text()), {"percent": TAP_BRIGHTNESS_PERCENT})

    async def test_tapping_the_tile_off_asks_the_host_for_zero(self):
        self.write_state(on=True, percent=20.0)
        broker = FakeBroker([(f"{PREFIX}/{SET_ON}", b"false")])
        surface = self.build_surface(broker)

        await surface.serve_one_connection()

        self.assertEqual(json.loads(self.command_path.read_text()), {"percent": 0.0})

    async def test_dragging_the_slider_asks_the_host_for_that_level(self):
        self.write_state(on=True, percent=20.0)
        broker = FakeBroker([(f"{PREFIX}/{SET_BRIGHTNESS}", b"35")])
        surface = self.build_surface(broker)

        await surface.serve_one_connection()

        self.assertEqual(json.loads(self.command_path.read_text()), {"percent": 35.0})

    async def test_a_slider_value_above_the_scale_is_clamped_to_full(self):
        self.write_state(on=True, percent=20.0)
        broker = FakeBroker([(f"{PREFIX}/{SET_BRIGHTNESS}", b"140")])
        surface = self.build_surface(broker)

        await surface.serve_one_connection()

        self.assertEqual(json.loads(self.command_path.read_text()), {"percent": 100.0})

    async def test_an_unreadable_brightness_changes_nothing(self):
        self.write_state(on=True, percent=20.0)
        broker = FakeBroker([(f"{PREFIX}/{SET_BRIGHTNESS}", "дуже яскраво".encode())])
        surface = self.build_surface(broker)

        await surface.serve_one_connection()

        self.assertFalse(self.command_path.exists())

    async def test_a_slider_drag_is_answered_with_the_level_asked_for_not_the_one_still_fading(self):
        self.write_state(on=True, percent=3.0)
        broker = FakeBroker([(f"{PREFIX}/{SET_BRIGHTNESS}", b"40")])
        surface = self.build_surface(broker)

        await surface.serve_one_connection()

        self.assertEqual(broker.last_published()[f"{PREFIX}/panel-light/brightness"], "40")
        self.assertEqual(broker.last_published()[f"{PREFIX}/panel-light/on"], "true")

    async def test_the_lamp_is_not_exposed_while_the_strip_is_switched_off_in_settings(self):
        broker = FakeBroker()
        surface = MqttSurface(host="broker", port=1883, topic_prefix=PREFIX, client_factory=lambda _: broker)
        register_panel_light_listeners(
            surface,
            MqttContext(settings=build_settings(PANEL_LIGHT_ENABLED=False), panel_light=self.panel_light),
        )

        await surface.serve_one_connection()

        self.assertEqual(broker.last_published(), {})
