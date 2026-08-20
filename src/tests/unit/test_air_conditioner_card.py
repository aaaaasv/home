import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from src.bot.handlers.air_conditioner.formatting import render_air_conditioner
from src.bot.handlers.air_conditioner.keyboards import (
    AirConditionerAction,
    AirConditionerCallback,
    build_air_conditioner_keyboard,
    build_air_conditioner_stop_keyboard,
)
from src.modules.air_conditioner.domain import AirConditionerFanSpeed, AirConditionerMode, AirConditionerState
from src.modules.plant_care.services.room_climate_sensor import RoomClimate
from src.modules.weather.domain import VentilationEffect

MOMENT = datetime(2026, 7, 20, 12, 47, tzinfo=ZoneInfo("Europe/Kyiv"))


def build_state(**overrides) -> AirConditionerState:
    defaults = dict(
        is_on=True,
        mode=AirConditionerMode.COOL,
        target_temperature_celsius=24,
        room_temperature_celsius=26,
    )
    defaults.update(overrides)
    return AirConditionerState(**defaults)


class RenderAirConditionerTestCase(unittest.TestCase):
    def test_render_air_conditioner_when_running_says_what_it_is_doing(self):
        rendered = render_air_conditioner(build_state(), "вітальня", MOMENT)

        self.assertEqual(
            rendered,
            "❄️ <b>Кондиціонер</b> — вітальня\n\nохолоджує до 24°\nу кімнаті 26°\n\n<i>оновлено 12:47</i>",
        )

    def test_render_air_conditioner_when_off_keeps_the_last_target(self):
        rendered = render_air_conditioner(build_state(is_on=False), "вітальня", MOMENT)

        self.assertIn("вимкнено · було 24°", rendered)

    def test_render_air_conditioner_without_a_room_reading_omits_that_line(self):
        rendered = render_air_conditioner(build_state(room_temperature_celsius=None), "вітальня", MOMENT)

        self.assertNotIn("у кімнаті", rendered)


class BuildAirConditionerKeyboardTestCase(unittest.TestCase):
    def button_texts(self, state: AirConditionerState) -> list[str]:
        markup = build_air_conditioner_keyboard(state)
        return [button.text for row in markup.inline_keyboard for button in row]

    def test_build_air_conditioner_keyboard_when_running_offers_to_turn_it_off(self):
        self.assertIn("Вимкнути", self.button_texts(build_state()))

    def test_build_air_conditioner_keyboard_when_off_offers_to_turn_it_on(self):
        self.assertIn("Увімкнути", self.button_texts(build_state(is_on=False)))

    def test_build_air_conditioner_keyboard_marks_the_active_mode(self):
        texts = self.button_texts(build_state(mode=AirConditionerMode.DRY))

        self.assertIn("✓ осушення", texts)
        self.assertIn("❄️ холод", texts)

    def test_build_air_conditioner_keyboard_shows_the_target_between_the_steps(self):
        self.assertEqual(self.button_texts(build_state())[1:4], ["−1°", "24°", "+1°"])

    def test_build_air_conditioner_keyboard_never_offers_heating(self):
        self.assertNotIn("тепло", self.button_texts(build_state()))

    def test_build_air_conditioner_callback_payload_fits_the_telegram_limit(self):
        payload = AirConditionerCallback(action="mode", mode=AirConditionerMode.DRY).pack()

        self.assertLessEqual(len(payload.encode()), 64)

    def power_callback(self, state: AirConditionerState) -> AirConditionerCallback:
        markup = build_air_conditioner_keyboard(state)
        return AirConditionerCallback.unpack(markup.inline_keyboard[0][0].callback_data)

    def test_power_button_on_a_running_unit_asks_to_turn_it_off(self):
        # the payload must carry the end state the label promises: a bare toggle would undo a press someone else
        # already made, switching the unit back on when both of them wanted it off
        self.assertFalse(self.power_callback(build_state(is_on=True)).turn_on)

    def test_power_button_on_a_stopped_unit_asks_to_turn_it_on(self):
        self.assertTrue(self.power_callback(build_state(is_on=False)).turn_on)


class BuildAirConditionerStopKeyboardTestCase(unittest.TestCase):
    def test_stop_keyboard_button_dismisses_its_own_alert_card(self):
        markup = build_air_conditioner_stop_keyboard()

        callback = AirConditionerCallback.unpack(markup.inline_keyboard[0][0].callback_data)

        self.assertEqual(callback.action, AirConditionerAction.STOP_AND_DISMISS)


class AirConditionerAirflowControlsTestCase(unittest.TestCase):
    def button_texts(self, state: AirConditionerState) -> list[str]:
        markup = build_air_conditioner_keyboard(state)
        return [button.text for row in markup.inline_keyboard for button in row]

    def payloads(self, state: AirConditionerState) -> list[AirConditionerCallback]:
        markup = build_air_conditioner_keyboard(state)
        return [AirConditionerCallback.unpack(button.callback_data) for row in markup.inline_keyboard for button in row]

    def test_airflow_buttons_appear_while_the_unit_runs(self):
        texts = self.button_texts(build_state(is_on=True))

        self.assertIn("🌀 обдув: авто", texts)
        self.assertIn("🚀 турбо", texts)
        self.assertIn("🔇 тихо", texts)
        self.assertIn("💧 просушка", texts)

    def test_airflow_buttons_are_hidden_when_the_unit_is_off(self):
        texts = self.button_texts(build_state(is_on=False))

        self.assertNotIn("🌀 обдув: авто", texts)
        self.assertNotIn("🚀 турбо", texts)

    def test_fan_button_names_the_current_speed(self):
        texts = self.button_texts(build_state(fan_speed=AirConditionerFanSpeed.HIGH))

        self.assertIn("🌀 обдув: висока", texts)

    def test_active_toggle_swaps_its_icon_for_a_tick(self):
        texts = self.button_texts(build_state(turbo=True))

        self.assertIn("✓ турбо", texts)
        self.assertNotIn("🚀 турбо", texts)

    def test_fan_button_steps_to_the_next_speed(self):
        fan = next(
            p
            for p in self.payloads(build_state(fan_speed=AirConditionerFanSpeed.LOW))
            if p.action == AirConditionerAction.SET_FAN
        )

        self.assertEqual(fan.fan_speed, AirConditionerFanSpeed.MEDIUM)

    def test_fan_button_wraps_from_high_back_to_auto(self):
        fan = next(
            p
            for p in self.payloads(build_state(fan_speed=AirConditionerFanSpeed.HIGH))
            if p.action == AirConditionerAction.SET_FAN
        )

        self.assertEqual(fan.fan_speed, AirConditionerFanSpeed.AUTO)

    def test_turbo_toggle_promises_the_opposite_of_the_current_state(self):
        turbo = next(p for p in self.payloads(build_state(turbo=True)) if p.action == AirConditionerAction.TOGGLE_TURBO)

        self.assertFalse(turbo.turn_on)

    def test_air_conditioner_fan_callback_payload_fits_the_telegram_limit(self):
        payload = AirConditionerCallback(
            action=AirConditionerAction.SET_FAN, fan_speed=AirConditionerFanSpeed.MEDIUM
        ).pack()

        self.assertLessEqual(len(payload.encode()), 64)


class RenderAirConditionerExtrasTestCase(unittest.TestCase):
    def test_render_air_conditioner_in_fan_mode_names_no_target(self):
        rendered = render_air_conditioner(build_state(mode=AirConditionerMode.FAN), "вітальня", MOMENT)

        self.assertIn("вентиляція · без охолодження", rendered)
        self.assertNotIn("24°", rendered)

    def test_render_air_conditioner_prefers_the_room_sensor_over_the_units_own(self):
        indoor = RoomClimate(temperature_celsius=25.1, relative_humidity_percent=57.6)

        rendered = render_air_conditioner(build_state(), "вітальня", MOMENT, indoor)

        self.assertIn("у кімнаті 25° · вологість 58%", rendered)

    def test_render_air_conditioner_suggests_windows_when_airing_would_beat_cooling(self):
        indoor = RoomClimate(temperature_celsius=25.1, relative_humidity_percent=57.6)

        rendered = render_air_conditioner(build_state(), "вітальня", MOMENT, indoor, VentilationEffect.DRIER)

        self.assertIn("🪟 надворі сухіше — краще відчинити вікна", rendered)

    def test_render_air_conditioner_stays_quiet_when_airing_would_not_help(self):
        indoor = RoomClimate(temperature_celsius=25.1, relative_humidity_percent=57.6)

        rendered = render_air_conditioner(build_state(), "вітальня", MOMENT, indoor, VentilationEffect.WETTER)

        self.assertNotIn("вікна", rendered)

    def test_render_air_conditioner_lists_active_airflow_badges(self):
        rendered = render_air_conditioner(build_state(turbo=True, xfan=True), "вітальня", MOMENT)

        self.assertIn("🚀 турбо · 💧 просушка", rendered)

    def test_render_air_conditioner_omits_badges_when_nothing_is_active(self):
        rendered = render_air_conditioner(build_state(), "вітальня", MOMENT)

        self.assertNotIn("турбо", rendered)

    def test_render_air_conditioner_hides_stale_badges_when_off(self):
        rendered = render_air_conditioner(build_state(is_on=False, turbo=True), "вітальня", MOMENT)

        self.assertNotIn("турбо", rendered)
