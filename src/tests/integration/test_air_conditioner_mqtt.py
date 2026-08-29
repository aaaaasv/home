import unittest
from dataclasses import dataclass

from src.common.config import Settings
from src.modules.air_conditioner.domain import AirConditionerMode, AirConditionerState
from src.mqtt.air_conditioner import register_listeners
from src.mqtt.surface import MqttContext, MqttSurface

PREFIX = "home-bot"


@dataclass(frozen=True)
class FakeMessage:
    topic: str
    payload: bytes


class FakeBroker:
    """Hands over the queued messages once and then ends the connection, so one session is one test."""

    def __init__(self, incoming: list[tuple[str, bytes]] | None = None):
        self.incoming = incoming or []
        self.subscriptions: list[str] = []
        self.published: list[tuple[str, str]] = []
        self.retained: set[str] = set()

    async def __aenter__(self) -> "FakeBroker":
        return self

    async def __aexit__(self, *exception: object) -> None:
        return None

    async def subscribe(self, topic: str, qos: int = 0) -> None:
        self.subscriptions.append(topic)

    async def publish(self, topic: str, payload: bytes, qos: int = 0, retain: bool = False) -> None:
        self.published.append((topic, payload.decode()))
        if retain:
            self.retained.add(topic)

    @property
    def messages(self):
        async def deliver():
            for topic, payload in self.incoming:
                yield FakeMessage(topic=topic, payload=payload)

        return deliver()

    def last_published(self) -> dict[str, str]:
        return dict(self.published)


class RecordingAirConditioner:
    """Answers with the state it was given, and remembers what was applied to it."""

    def __init__(self, state: AirConditionerState | None, applied_state: AirConditionerState | None = None):
        self.state = state
        self.applied_state = applied_state if applied_state is not None else state
        self.apply_calls: list[dict] = []
        self.busy = False

    async def read_state(self) -> AirConditionerState | None:
        return self.state

    async def apply(self, **requested) -> AirConditionerState | None:
        self.apply_calls.append(requested)
        return self.applied_state


def build_state(**overrides) -> AirConditionerState:
    defaults = dict(
        is_on=True, mode=AirConditionerMode.COOL, target_temperature_celsius=24, room_temperature_celsius=26
    )
    defaults.update(overrides)
    return AirConditionerState(**defaults)


def build_settings(**overrides) -> Settings:
    defaults = dict(
        TELEGRAM_BOT_TOKEN="123:abc",
        AIR_CONDITIONER_ENABLED=True,
        AIR_CONDITIONER_MIN_TEMPERATURE=16,
        AIR_CONDITIONER_MAX_TEMPERATURE=30,
        MQTT_PUBLISH_INTERVAL_SECONDS=3600,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def build_surface(broker: FakeBroker, air_conditioner, settings: Settings) -> MqttSurface:
    surface = MqttSurface(host="broker", port=1883, topic_prefix=PREFIX, client_factory=lambda _: broker)
    register_listeners(surface, MqttContext(settings=settings, air_conditioner=air_conditioner))
    return surface


class PublishAirConditionerStateTestCase(unittest.IsolatedAsyncioTestCase):
    """
    The unit as a thermostat on the broker, which is the whole of what a phone tile ever sees.

    the reading is published the moment the connection opens rather than after the first interval, because a
    controller that starts while the bot is already running would otherwise show an empty tile for a minute.
    """

    async def test_publishing_a_cooling_unit_puts_every_thermostat_topic_on_the_broker(self):
        broker = FakeBroker()
        surface = build_surface(broker, RecordingAirConditioner(build_state()), build_settings())

        await surface.serve_one_connection()

        self.assertEqual(
            broker.last_published(),
            {
                f"{PREFIX}/air-conditioner/available": "true",
                f"{PREFIX}/air-conditioner/current-state": "cool",
                f"{PREFIX}/air-conditioner/target-state": "cool",
                f"{PREFIX}/air-conditioner/current-temperature": "26",
                f"{PREFIX}/air-conditioner/target-temperature": "24",
            },
        )

    async def test_publishing_a_unit_that_is_off_reports_off_for_both_states(self):
        broker = FakeBroker()
        surface = build_surface(broker, RecordingAirConditioner(build_state(is_on=False)), build_settings())

        await surface.serve_one_connection()

        self.assertEqual(broker.last_published()[f"{PREFIX}/air-conditioner/current-state"], "off")
        self.assertEqual(broker.last_published()[f"{PREFIX}/air-conditioner/target-state"], "off")

    async def test_publishing_a_unit_in_drying_mode_reports_it_as_auto_because_a_thermostat_has_no_word_for_it(self):
        broker = FakeBroker()
        surface = build_surface(
            broker, RecordingAirConditioner(build_state(mode=AirConditionerMode.DRY)), build_settings()
        )

        await surface.serve_one_connection()

        self.assertEqual(broker.last_published()[f"{PREFIX}/air-conditioner/target-state"], "auto")
        self.assertEqual(broker.last_published()[f"{PREFIX}/air-conditioner/current-state"], "cool")

    async def test_publishing_an_unreachable_unit_marks_it_unavailable_and_publishes_nothing_else(self):
        broker = FakeBroker()
        surface = build_surface(broker, RecordingAirConditioner(None), build_settings())

        await surface.serve_one_connection()

        self.assertEqual(broker.last_published(), {f"{PREFIX}/air-conditioner/available": "false"})

    async def test_publishing_a_unit_without_its_own_thermometer_omits_the_current_temperature(self):
        broker = FakeBroker()
        state = build_state(room_temperature_celsius=None)
        surface = build_surface(broker, RecordingAirConditioner(state), build_settings())

        await surface.serve_one_connection()

        self.assertNotIn(f"{PREFIX}/air-conditioner/current-temperature", broker.last_published())

    async def test_every_reading_is_retained_so_a_controller_starting_later_sees_the_current_state(self):
        broker = FakeBroker()
        surface = build_surface(broker, RecordingAirConditioner(build_state()), build_settings())

        await surface.serve_one_connection()

        self.assertEqual(broker.retained, {topic for topic, _ in broker.published})

    async def test_a_flat_with_the_air_conditioner_switched_off_publishes_and_subscribes_to_nothing(self):
        broker = FakeBroker()
        settings = build_settings(AIR_CONDITIONER_ENABLED=False)
        surface = build_surface(broker, RecordingAirConditioner(build_state()), settings)

        await surface.serve_one_connection()

        self.assertEqual((broker.published, broker.subscriptions), ([], []))


class CommandAirConditionerTestCase(unittest.IsolatedAsyncioTestCase):
    """
    A tap on a phone tile, arriving as one payload on one topic.

    the reply is the unit's own new state rather than an echo of what was asked, so a tile that asked for
    something the unit refused settles back onto the truth instead of lying until the next interval.
    """

    async def test_the_surface_subscribes_to_both_command_topics(self):
        broker = FakeBroker()
        surface = build_surface(broker, RecordingAirConditioner(build_state()), build_settings())

        await surface.serve_one_connection()

        self.assertEqual(
            sorted(broker.subscriptions),
            [f"{PREFIX}/air-conditioner/set/target-state", f"{PREFIX}/air-conditioner/set/target-temperature"],
        )

    async def test_setting_the_target_state_to_off_turns_the_unit_off(self):
        broker = FakeBroker([(f"{PREFIX}/air-conditioner/set/target-state", b"off")])
        air_conditioner = RecordingAirConditioner(build_state(), applied_state=build_state(is_on=False))
        surface = build_surface(broker, air_conditioner, build_settings())

        await surface.serve_one_connection()

        self.assertEqual(air_conditioner.apply_calls, [{"is_on": False}])

    async def test_setting_the_target_state_to_heat_switches_the_mode_and_turns_the_unit_on(self):
        broker = FakeBroker([(f"{PREFIX}/air-conditioner/set/target-state", b"heat")])
        air_conditioner = RecordingAirConditioner(
            build_state(), applied_state=build_state(mode=AirConditionerMode.HEAT)
        )
        surface = build_surface(broker, air_conditioner, build_settings())

        await surface.serve_one_connection()

        self.assertEqual(air_conditioner.apply_calls, [{"is_on": True, "mode": AirConditionerMode.HEAT}])

    async def test_setting_the_target_state_republishes_the_new_state_without_waiting_for_the_next_interval(self):
        broker = FakeBroker([(f"{PREFIX}/air-conditioner/set/target-state", b"off")])
        air_conditioner = RecordingAirConditioner(build_state(), applied_state=build_state(is_on=False))
        surface = build_surface(broker, air_conditioner, build_settings())

        await surface.serve_one_connection()

        self.assertEqual(broker.last_published()[f"{PREFIX}/air-conditioner/target-state"], "off")

    async def test_setting_an_unknown_target_state_leaves_the_unit_untouched(self):
        broker = FakeBroker([(f"{PREFIX}/air-conditioner/set/target-state", b"dehumidify")])
        air_conditioner = RecordingAirConditioner(build_state())
        surface = build_surface(broker, air_conditioner, build_settings())

        await surface.serve_one_connection()

        self.assertEqual(air_conditioner.apply_calls, [])

    async def test_setting_a_half_degree_target_temperature_rounds_it_to_what_the_unit_takes(self):
        broker = FakeBroker([(f"{PREFIX}/air-conditioner/set/target-temperature", b"22.5")])
        air_conditioner = RecordingAirConditioner(build_state())
        surface = build_surface(broker, air_conditioner, build_settings())

        await surface.serve_one_connection()

        self.assertEqual(air_conditioner.apply_calls, [{"target_temperature_celsius": 22}])

    async def test_setting_a_target_temperature_above_the_maximum_clamps_it_to_the_maximum(self):
        broker = FakeBroker([(f"{PREFIX}/air-conditioner/set/target-temperature", b"35")])
        air_conditioner = RecordingAirConditioner(build_state())
        surface = build_surface(broker, air_conditioner, build_settings())

        await surface.serve_one_connection()

        self.assertEqual(air_conditioner.apply_calls, [{"target_temperature_celsius": 30}])

    async def test_setting_a_target_temperature_below_the_minimum_clamps_it_to_the_minimum(self):
        broker = FakeBroker([(f"{PREFIX}/air-conditioner/set/target-temperature", b"5")])
        air_conditioner = RecordingAirConditioner(build_state())
        surface = build_surface(broker, air_conditioner, build_settings())

        await surface.serve_one_connection()

        self.assertEqual(air_conditioner.apply_calls, [{"target_temperature_celsius": 16}])

    async def test_setting_an_unreadable_target_temperature_leaves_the_unit_untouched(self):
        broker = FakeBroker([(f"{PREFIX}/air-conditioner/set/target-temperature", b"warm")])
        air_conditioner = RecordingAirConditioner(build_state())
        surface = build_surface(broker, air_conditioner, build_settings())

        await surface.serve_one_connection()

        self.assertEqual(air_conditioner.apply_calls, [])

    async def test_a_message_on_a_topic_nobody_registered_is_ignored(self):
        broker = FakeBroker([(f"{PREFIX}/air-conditioner/set/fan-speed", b"high")])
        air_conditioner = RecordingAirConditioner(build_state())
        surface = build_surface(broker, air_conditioner, build_settings())

        await surface.serve_one_connection()

        self.assertEqual(air_conditioner.apply_calls, [])


class AnnounceMqttLossTestCase(unittest.IsolatedAsyncioTestCase):
    """
    The broker speaks for the bot when the bot cannot.

    without it a tile keeps showing the last reading it saw, so a bot that died overnight looks like a unit
    that is simply off — the silent failure that disqualified a leak sensor from this house.
    """

    async def test_the_air_conditioner_claims_the_farewell_message_on_its_availability_topic(self):
        surface = build_surface(FakeBroker(), RecordingAirConditioner(build_state()), build_settings())

        farewell = surface.farewell

        self.assertEqual(farewell, ("air-conditioner/available", "false"))

    async def test_stopping_the_surface_marks_the_unit_unavailable_before_the_connection_closes(self):
        broker = FakeBroker()
        surface = build_surface(broker, RecordingAirConditioner(build_state()), build_settings())
        await surface.start()

        await surface.stop()

        self.assertEqual(broker.published[-1], (f"{PREFIX}/air-conditioner/available", "false"))

    async def test_claiming_the_farewell_message_twice_fails_rather_than_taking_it_from_the_first_module(self):
        surface = build_surface(FakeBroker(), RecordingAirConditioner(build_state()), build_settings())

        with self.assertRaises(RuntimeError) as context:
            surface.announce_loss_as("something-else/available", "false")

        self.assertEqual(str(context.exception), "the mqtt farewell message is already claimed by another module")
