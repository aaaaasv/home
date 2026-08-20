import unittest

from src.bot.handlers.air_conditioner.card import _apply_action
from src.bot.handlers.air_conditioner.keyboards import AirConditionerAction, AirConditionerCallback
from src.modules.air_conditioner.domain import AirConditionerFanSpeed, AirConditionerMode, AirConditionerState


def build_state(**overrides) -> AirConditionerState:
    defaults = dict(
        is_on=True, mode=AirConditionerMode.COOL, target_temperature_celsius=24, room_temperature_celsius=26
    )
    defaults.update(overrides)
    return AirConditionerState(**defaults)


class RecordingAirConditioner:
    def __init__(self, state: AirConditionerState):
        self._state = state
        self.apply_calls: list[dict] = []

    async def read_state(self) -> AirConditionerState:
        return self._state

    async def apply(self, **kwargs) -> AirConditionerState:
        self.apply_calls.append(kwargs)
        return self._state


class ApplyAirConditionerActionTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_set_fan_applies_the_speed_and_clears_turbo_and_quiet(self):
        air_conditioner = RecordingAirConditioner(build_state())
        callback = AirConditionerCallback(action=AirConditionerAction.SET_FAN, fan_speed=AirConditionerFanSpeed.HIGH)

        await _apply_action(callback, build_state(), air_conditioner)

        self.assertEqual(
            air_conditioner.apply_calls, [{"fan_speed": AirConditionerFanSpeed.HIGH, "turbo": False, "quiet": False}]
        )

    async def test_turning_turbo_on_drops_quiet(self):
        air_conditioner = RecordingAirConditioner(build_state())
        callback = AirConditionerCallback(action=AirConditionerAction.TOGGLE_TURBO, turn_on=True)

        await _apply_action(callback, build_state(), air_conditioner)

        self.assertEqual(air_conditioner.apply_calls, [{"turbo": True, "quiet": False}])

    async def test_turning_turbo_off_leaves_quiet_untouched(self):
        air_conditioner = RecordingAirConditioner(build_state(turbo=True))
        callback = AirConditionerCallback(action=AirConditionerAction.TOGGLE_TURBO, turn_on=False)

        await _apply_action(callback, build_state(turbo=True), air_conditioner)

        self.assertEqual(air_conditioner.apply_calls, [{"turbo": False, "quiet": None}])

    async def test_turning_quiet_on_drops_turbo(self):
        air_conditioner = RecordingAirConditioner(build_state())
        callback = AirConditionerCallback(action=AirConditionerAction.TOGGLE_QUIET, turn_on=True)

        await _apply_action(callback, build_state(), air_conditioner)

        self.assertEqual(air_conditioner.apply_calls, [{"quiet": True, "turbo": False}])

    async def test_toggling_xfan_touches_only_xfan(self):
        air_conditioner = RecordingAirConditioner(build_state())
        callback = AirConditionerCallback(action=AirConditionerAction.TOGGLE_XFAN, turn_on=True)

        await _apply_action(callback, build_state(), air_conditioner)

        self.assertEqual(air_conditioner.apply_calls, [{"xfan": True}])
