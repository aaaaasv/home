import unittest

from src.bot.handlers.air_conditioner.card import stop_air_conditioner_and_dismiss_alert
from src.bot.handlers.air_conditioner.messages import (
    AIR_CONDITIONER_ALREADY_OFF,
    AIR_CONDITIONER_TURNED_OFF,
    AIR_CONDITIONER_UNREACHABLE,
)
from src.modules.air_conditioner.domain import AirConditionerMode, AirConditionerState


def build_state(is_on: bool) -> AirConditionerState:
    return AirConditionerState(
        is_on=is_on, mode=AirConditionerMode.COOL, target_temperature_celsius=24, room_temperature_celsius=26
    )


class StubAirConditioner:
    def __init__(self, state: AirConditionerState | None, apply_result: AirConditionerState | None = None):
        self._state = state
        self._apply_result = apply_result
        self.applied_power: list[bool | None] = []

    async def read_state(self) -> AirConditionerState | None:
        return self._state

    async def apply(self, is_on=None, mode=None, target_temperature_celsius=None) -> AirConditionerState | None:
        self.applied_power.append(is_on)
        return self._apply_result


class RecordingAlertMessage:
    def __init__(self):
        self.deleted = False

    async def delete(self) -> None:
        self.deleted = True


class RecordingCallback:
    def __init__(self):
        self.message = RecordingAlertMessage()
        self.answers: list[dict] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append({"text": text, "show_alert": show_alert})


class StopAndDismissAlertTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_stop_and_dismiss_while_running_turns_off_and_deletes_the_card(self):
        air_conditioner = StubAirConditioner(build_state(is_on=True), apply_result=build_state(is_on=False))
        callback = RecordingCallback()

        await stop_air_conditioner_and_dismiss_alert(callback, air_conditioner)

        self.assertEqual(air_conditioner.applied_power, [False])
        self.assertEqual(callback.answers, [{"text": AIR_CONDITIONER_TURNED_OFF, "show_alert": False}])
        self.assertTrue(callback.message.deleted)

    async def test_stop_and_dismiss_when_already_off_deletes_the_card_without_touching_the_unit(self):
        air_conditioner = StubAirConditioner(build_state(is_on=False))
        callback = RecordingCallback()

        await stop_air_conditioner_and_dismiss_alert(callback, air_conditioner)

        self.assertEqual(air_conditioner.applied_power, [])
        self.assertEqual(callback.answers, [{"text": AIR_CONDITIONER_ALREADY_OFF, "show_alert": False}])
        self.assertTrue(callback.message.deleted)

    async def test_stop_and_dismiss_when_unreachable_keeps_the_card(self):
        air_conditioner = StubAirConditioner(None)
        callback = RecordingCallback()

        await stop_air_conditioner_and_dismiss_alert(callback, air_conditioner)

        self.assertEqual(air_conditioner.applied_power, [])
        self.assertEqual(callback.answers, [{"text": AIR_CONDITIONER_UNREACHABLE, "show_alert": True}])
        self.assertFalse(callback.message.deleted)

    async def test_stop_and_dismiss_when_the_turn_off_fails_keeps_the_card(self):
        air_conditioner = StubAirConditioner(build_state(is_on=True), apply_result=None)
        callback = RecordingCallback()

        await stop_air_conditioner_and_dismiss_alert(callback, air_conditioner)

        self.assertEqual(air_conditioner.applied_power, [False])
        self.assertEqual(callback.answers, [{"text": AIR_CONDITIONER_UNREACHABLE, "show_alert": True}])
        self.assertFalse(callback.message.deleted)
