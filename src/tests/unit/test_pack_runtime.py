import unittest
from datetime import datetime, timedelta, timezone

from src.modules.power.domain import PackWarning, UpsState
from src.modules.power.pack_runtime import PACK_RUNTIME_CURVE, classify_pack, estimate_pack_runtime

NOW = datetime(2026, 10, 14, 20, 30, tzinfo=timezone.utc)

WARNING_AT = timedelta(minutes=60)
GOODBYE_AT = timedelta(minutes=10)


def hat(battery_volts: float, mains_present: bool = False, battery_percent: float = 50.0) -> UpsState:
    return UpsState(
        mains_present=mains_present, battery_volts=battery_volts, battery_percent=battery_percent, as_of=NOW
    )


class EstimatePackRuntimeTestCase(unittest.TestCase):
    """
    The one number the board could never give, read off two discharges that ran to the hat's own cut-off.

    the gauge's percent is not in this file at all, and that is the point: it reported 15% with an hour and
    twenty minutes left and 0.1% with thirty-three minutes left, so no average rate fits both ends.
    """

    def test_estimate_at_every_measured_step_returns_that_step(self):
        estimates = [estimate_pack_runtime(volts) for volts, _ in PACK_RUNTIME_CURVE]

        self.assertEqual(estimates, [timedelta(minutes=minutes) for _, minutes in PACK_RUNTIME_CURVE])

    def test_estimate_between_two_steps_interpolates_between_their_minutes(self):
        estimate = estimate_pack_runtime(3.575)

        self.assertEqual(estimate, timedelta(minutes=74))

    def test_estimate_for_a_pack_above_the_curve_gives_the_whole_measured_run(self):
        estimate = estimate_pack_runtime(4.199)

        self.assertEqual(estimate, timedelta(minutes=345))

    def test_estimate_at_the_voltage_the_agent_halts_on_is_nothing_left(self):
        estimate = estimate_pack_runtime(3.40)

        self.assertEqual(estimate, timedelta(0))

    def test_estimate_below_the_halt_voltage_is_nothing_left_rather_than_a_negative_run(self):
        estimate = estimate_pack_runtime(3.31)

        self.assertEqual(estimate, timedelta(0))

    def test_estimate_at_the_voltage_the_gauge_called_fifteen_percent_is_the_measured_hour_and_a_half(self):
        """The night of 14.10: 3.60 V read 17% on the gauge and ran for another 1 h 25 min."""
        estimate = estimate_pack_runtime(3.60)

        self.assertEqual(estimate, timedelta(minutes=86))


class ClassifyPackTestCase(unittest.TestCase):
    """
    Which of the two moments worth a push this reading is — and silence is the answer almost every time.

    both thresholds are times and not charges, so the same code decides the message and the number in it.
    """

    def test_classify_a_pack_with_hours_left_is_nothing_worth_saying(self):
        warning = classify_pack(hat(battery_volts=3.90), WARNING_AT, GOODBYE_AT)

        self.assertIsNone(warning)

    def test_classify_a_pack_just_over_the_hour_still_says_nothing(self):
        warning = classify_pack(hat(battery_volts=3.55), WARNING_AT, GOODBYE_AT)

        self.assertIsNone(warning)

    def test_classify_a_pack_with_under_an_hour_left_is_the_low_warning(self):
        warning = classify_pack(hat(battery_volts=3.54), WARNING_AT, GOODBYE_AT)

        self.assertEqual(warning, PackWarning.LOW)

    def test_classify_a_pack_ten_minutes_from_the_halt_is_the_goodbye(self):
        warning = classify_pack(hat(battery_volts=3.42), WARNING_AT, GOODBYE_AT)

        self.assertEqual(warning, PackWarning.HALTING)

    def test_classify_an_empty_pack_on_a_live_socket_is_nothing_because_it_is_charging(self):
        warning = classify_pack(hat(battery_volts=3.42, mains_present=True), WARNING_AT, GOODBYE_AT)

        self.assertIsNone(warning)

    def test_classify_a_hat_that_cannot_be_read_is_nothing_rather_than_an_empty_pack(self):
        warning = classify_pack(None, WARNING_AT, GOODBYE_AT)

        self.assertIsNone(warning)
