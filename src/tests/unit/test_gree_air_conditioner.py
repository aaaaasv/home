import unittest

from src.infrastructure.adapters.gree_air_conditioner import GreeAirConditioner
from src.modules.air_conditioner.domain import AirConditionerFanSpeed, AirConditionerMode

FULL_PROPERTIES = {
    "Pow": 1,
    "Mod": 1,
    "SetTem": 24,
    "TemSen": 66,
    "WdSpd": 0,
    "Health": 1,
    "Lig": 1,
}
# the reader waits for a full column set (>= 10 keys) before it trusts a reply as the unit's own
REPLY_PROPERTIES = {**FULL_PROPERTIES, "SwhSlp": 0, "SlpMod": 0, "Quiet": 0, "Air": 0}


class FakeDevice:
    def __init__(self, properties: dict):
        self.raw_properties = properties
        self.closed = False
        self.pushed = False
        self.power = None
        self.mode = None
        self.target_temperature = None
        self.fan_speed = None
        self.turbo = None
        self.quiet = None
        self.xfan = None

    async def update_state(self) -> None:
        pass

    async def push_state_update(self) -> None:
        self.pushed = True

    def close(self) -> None:
        self.closed = True


class ToStateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.air_conditioner = GreeAirConditioner(host="192.0.2.10", mac="00005e005301", name="вітальня")

    def test_to_state_reads_power_mode_target_and_room_temperature(self):
        state = self.air_conditioner._to_state(FULL_PROPERTIES)

        self.assertTrue(state.is_on)
        self.assertEqual(state.mode, AirConditionerMode.COOL)
        self.assertEqual(state.target_temperature_celsius, 24)
        self.assertEqual(state.room_temperature_celsius, 26)

    def test_to_state_maps_every_mode_code(self):
        modes = {
            code: self.air_conditioner._to_state({**FULL_PROPERTIES, "Mod": code}).mode for code in (0, 1, 2, 3, 4)
        }

        self.assertEqual(
            modes,
            {
                0: AirConditionerMode.AUTO,
                1: AirConditionerMode.COOL,
                2: AirConditionerMode.DRY,
                3: AirConditionerMode.FAN,
                4: AirConditionerMode.HEAT,
            },
        )

    def test_to_state_without_a_room_reading_leaves_it_unset(self):
        state = self.air_conditioner._to_state({**FULL_PROPERTIES, "TemSen": 0})

        self.assertIsNone(state.room_temperature_celsius)

    def test_to_state_reads_fan_speed_turbo_quiet_and_xfan(self):
        state = self.air_conditioner._to_state({**FULL_PROPERTIES, "WdSpd": 5, "Tur": 1, "Quiet": 2, "Blo": 1})

        self.assertEqual(state.fan_speed, AirConditionerFanSpeed.HIGH)
        self.assertTrue(state.turbo)
        self.assertTrue(state.quiet)
        self.assertTrue(state.xfan)

    def test_to_state_leaves_the_airflow_flags_off_by_default(self):
        state = self.air_conditioner._to_state(FULL_PROPERTIES)

        self.assertEqual(state.fan_speed, AirConditionerFanSpeed.AUTO)
        self.assertFalse(state.turbo)
        self.assertFalse(state.quiet)
        self.assertFalse(state.xfan)

    def test_to_state_folds_the_six_fan_steps_onto_four(self):
        speeds = {
            code: self.air_conditioner._to_state({**FULL_PROPERTIES, "WdSpd": code}).fan_speed for code in range(6)
        }

        self.assertEqual(
            speeds,
            {
                0: AirConditionerFanSpeed.AUTO,
                1: AirConditionerFanSpeed.LOW,
                2: AirConditionerFanSpeed.LOW,
                3: AirConditionerFanSpeed.MEDIUM,
                4: AirConditionerFanSpeed.HIGH,
                5: AirConditionerFanSpeed.HIGH,
            },
        )

    def test_to_state_of_a_half_filled_reply_reports_nothing(self):
        # assigning a property fills the library's own dictionary with a single key — that is not a device reply
        self.assertIsNone(self.air_conditioner._to_state({"Pow": 1}))

    def test_to_state_of_an_empty_reply_reports_nothing(self):
        self.assertIsNone(self.air_conditioner._to_state({}))


class ReleaseSocketTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.air_conditioner = GreeAirConditioner(host="192.0.2.10", mac="00005e005301", name="вітальня")
        self.device = FakeDevice(dict(REPLY_PROPERTIES))

        async def connect() -> FakeDevice:
            return self.device

        self.air_conditioner._connect = connect

    async def test_read_state_closes_the_udp_socket(self):
        state = await self.air_conditioner.read_state()

        self.assertTrue(self.device.closed)
        self.assertEqual(state.target_temperature_celsius, 24)

    async def test_apply_closes_the_udp_socket(self):
        state = await self.air_conditioner.apply(is_on=True, target_temperature_celsius=22)

        self.assertTrue(self.device.pushed)
        self.assertTrue(self.device.closed)
        self.assertTrue(state.is_on)

    async def test_apply_writes_fan_speed_turbo_quiet_and_xfan(self):
        await self.air_conditioner.apply(fan_speed=AirConditionerFanSpeed.MEDIUM, turbo=True, quiet=False, xfan=True)

        self.assertEqual(self.device.fan_speed, 3)
        self.assertTrue(self.device.turbo)
        self.assertFalse(self.device.quiet)
        self.assertTrue(self.device.xfan)

    async def test_apply_leaves_airflow_untouched_when_not_asked(self):
        await self.air_conditioner.apply(target_temperature_celsius=22)

        self.assertIsNone(self.device.fan_speed)
        self.assertIsNone(self.device.turbo)
        self.assertIsNone(self.device.xfan)
