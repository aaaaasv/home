import unittest
from datetime import datetime, timedelta, timezone

from src.modules.power.services.conservation import (
    ConservationKind,
    ConservationLevel,
    ConservationMode,
    ConservationState,
    detect_completed_cycle,
    estimate_percent,
    evaluate,
)

STORED_AT = datetime(2027, 1, 1, 12, 0, tzinfo=timezone.utc)


def state(
    stored_percent: float,
    mode: ConservationMode = ConservationMode.OFF,
    stored_at: datetime = STORED_AT,
    last_cycle_at: datetime | None = None,
) -> ConservationState:
    return ConservationState(stored_percent=stored_percent, stored_at=stored_at, mode=mode, last_cycle_at=last_cycle_at)


class EstimatePercentTestCase(unittest.TestCase):
    def test_estimate_percent_off_mode_drops_point_eight_per_day(self):
        result = estimate_percent(state(60), STORED_AT + timedelta(days=10))

        self.assertEqual(result, 52.0)

    def test_estimate_percent_ups_mode_drops_four_per_day(self):
        result = estimate_percent(state(60, ConservationMode.UPS), STORED_AT + timedelta(days=5))

        self.assertEqual(result, 40.0)

    def test_estimate_percent_never_falls_below_zero(self):
        result = estimate_percent(state(60), STORED_AT + timedelta(days=100))

        self.assertEqual(result, 0.0)

    def test_estimate_percent_at_the_moment_of_storage_is_the_stored_charge(self):
        result = estimate_percent(state(73.5), STORED_AT)

        self.assertEqual(result, 73.5)


class ConsolidationBandTestCase(unittest.TestCase):
    def evaluate_fresh(self, stored_percent: float):
        # one hour after storage — inside the consolidation window, so the storage-moment band is what speaks
        return evaluate(state(stored_percent), STORED_AT + timedelta(hours=1))

    def test_evaluate_fresh_storage_at_or_below_five_percent_is_red_consolidation(self):
        advisory = self.evaluate_fresh(5)

        self.assertEqual(advisory.level, ConservationLevel.RED)
        self.assertEqual(advisory.kind, ConservationKind.CONSOLIDATION)
        self.assertEqual(advisory.target_percent, 60)

    def test_evaluate_fresh_storage_below_thirty_percent_is_yellow_consolidation(self):
        advisory = self.evaluate_fresh(29)

        self.assertEqual(advisory.level, ConservationLevel.YELLOW)
        self.assertEqual(advisory.kind, ConservationKind.CONSOLIDATION)

    def test_evaluate_fresh_storage_at_thirty_percent_is_green(self):
        advisory = self.evaluate_fresh(30)

        self.assertEqual(advisory.level, ConservationLevel.GREEN)
        self.assertEqual(advisory.kind, ConservationKind.CONSOLIDATION)

    def test_evaluate_fresh_storage_in_the_healthy_band_is_green(self):
        advisory = self.evaluate_fresh(60)

        self.assertEqual(advisory.level, ConservationLevel.GREEN)
        self.assertEqual(advisory.kind, ConservationKind.CONSOLIDATION)

    def test_evaluate_fresh_storage_at_ninety_percent_is_green(self):
        advisory = self.evaluate_fresh(90)

        self.assertEqual(advisory.level, ConservationLevel.GREEN)

    def test_evaluate_fresh_storage_above_ninety_percent_is_blue_consolidation(self):
        advisory = self.evaluate_fresh(95)

        self.assertEqual(advisory.level, ConservationLevel.BLUE)
        self.assertEqual(advisory.kind, ConservationKind.CONSOLIDATION)
        self.assertEqual(advisory.target_percent, 60)

    def test_evaluate_past_the_consolidation_window_stops_reporting_the_storage_band(self):
        # three days after storage at a healthy 60%, with no cycle or drift concern, nothing needs saying
        advisory = evaluate(state(60), STORED_AT + timedelta(days=3))

        self.assertIsNone(advisory)


class ZeroProtectionTestCase(unittest.TestCase):
    def test_evaluate_estimated_charge_at_twenty_percent_warns_yellow(self):
        # 50 days off at 0.8%/day: 60 − 40 = 20, past the consolidation window, cycle not yet due
        advisory = evaluate(state(60), STORED_AT + timedelta(days=50))

        self.assertEqual(advisory.level, ConservationLevel.YELLOW)
        self.assertEqual(advisory.kind, ConservationKind.ZERO_PROTECTION)
        self.assertEqual(advisory.estimated_percent, 20)
        self.assertEqual(advisory.target_percent, 60)

    def test_evaluate_estimated_charge_at_ten_percent_is_red(self):
        # 62.5 days off at 0.8%/day: 60 − 50 = 10
        advisory = evaluate(state(60), STORED_AT + timedelta(days=62, hours=12))

        self.assertEqual(advisory.level, ConservationLevel.RED)
        self.assertEqual(advisory.kind, ConservationKind.ZERO_PROTECTION)
        self.assertEqual(advisory.estimated_percent, 10)

    def test_evaluate_ups_mode_hits_zero_protection_quickly(self):
        # 13 days as a UPS at 4%/day: 60 − 52 = 8, already urgent
        advisory = evaluate(state(60, ConservationMode.UPS), STORED_AT + timedelta(days=13))

        self.assertEqual(advisory.level, ConservationLevel.RED)
        self.assertEqual(advisory.kind, ConservationKind.ZERO_PROTECTION)


class MaintenanceCycleTestCase(unittest.TestCase):
    def evaluate_at(self, days: int):
        # stored full so self-discharge never reaches the zero watch and the cycle timing is what speaks
        return evaluate(state(100), STORED_AT + timedelta(days=days))

    def test_evaluate_one_day_before_the_lead_window_says_nothing(self):
        advisory = self.evaluate_at(82)

        self.assertIsNone(advisory)

    def test_evaluate_at_the_lead_window_gives_a_green_heads_up(self):
        advisory = self.evaluate_at(83)

        self.assertEqual(advisory.level, ConservationLevel.GREEN)
        self.assertEqual(advisory.kind, ConservationKind.CYCLE_DUE)
        self.assertEqual(advisory.days_until_cycle, 7)

    def test_evaluate_at_ninety_days_the_cycle_is_due_yellow(self):
        advisory = self.evaluate_at(90)

        self.assertEqual(advisory.level, ConservationLevel.YELLOW)
        self.assertEqual(advisory.kind, ConservationKind.CYCLE_DUE)
        self.assertEqual(advisory.days_since_cycle, 90)
        self.assertEqual(advisory.days_until_cycle, 0)

    def test_evaluate_just_below_the_warranty_wall_is_still_a_yellow_cycle(self):
        # cycled 169 days ago but topped up 5 days back, so the pack still holds charge — the cycle is what's due,
        # not the warranty (that lands at 170) and not the zero watch
        cycled = state(60, stored_at=STORED_AT + timedelta(days=164), last_cycle_at=STORED_AT)

        advisory = evaluate(cycled, STORED_AT + timedelta(days=169))

        self.assertEqual(advisory.level, ConservationLevel.YELLOW)
        self.assertEqual(advisory.kind, ConservationKind.CYCLE_DUE)
        self.assertEqual(advisory.days_since_cycle, 169)

    def test_evaluate_counts_the_cycle_from_the_last_recorded_cycle(self):
        # last cycled at day 100, topped up at day 185, checked at day 190 → 90 days since the cycle
        cycled = state(60, stored_at=STORED_AT + timedelta(days=185), last_cycle_at=STORED_AT + timedelta(days=100))

        advisory = evaluate(cycled, STORED_AT + timedelta(days=190))

        self.assertEqual(advisory.kind, ConservationKind.CYCLE_DUE)
        self.assertEqual(advisory.days_since_cycle, 90)


class WarrantyTestCase(unittest.TestCase):
    def test_evaluate_at_the_warranty_alert_day_is_red_warranty(self):
        advisory = evaluate(state(100), STORED_AT + timedelta(days=170))

        self.assertEqual(advisory.level, ConservationLevel.RED)
        self.assertEqual(advisory.kind, ConservationKind.WARRANTY)
        self.assertEqual(advisory.days_since_cycle, 170)
        self.assertEqual(advisory.days_until_warranty, 10)

    def test_evaluate_past_the_warranty_wall_reports_zero_days_left(self):
        advisory = evaluate(state(100), STORED_AT + timedelta(days=185))

        self.assertEqual(advisory.level, ConservationLevel.RED)
        self.assertEqual(advisory.kind, ConservationKind.WARRANTY)
        self.assertEqual(advisory.days_until_warranty, 0)

    def test_evaluate_warranty_outranks_a_flat_battery(self):
        # both fire at 170 days off (battery long since floored at 0), warranty is the one that must be said
        advisory = evaluate(state(60), STORED_AT + timedelta(days=170))

        self.assertEqual(advisory.kind, ConservationKind.WARRANTY)


class DetectCompletedCycleTestCase(unittest.TestCase):
    def readings(self, *percents: float):
        return [(STORED_AT + timedelta(hours=index), percent) for index, percent in enumerate(percents)]

    def test_detect_completed_cycle_low_then_high_returns_the_high_moment(self):
        trace = self.readings(60, 30, 4, 40, 96)

        result = detect_completed_cycle(trace)

        self.assertEqual(result, STORED_AT + timedelta(hours=4))

    def test_detect_completed_cycle_at_the_exact_thresholds_fires(self):
        trace = self.readings(50, 5, 95)

        result = detect_completed_cycle(trace)

        self.assertEqual(result, STORED_AT + timedelta(hours=2))

    def test_detect_completed_cycle_high_without_a_preceding_low_is_none(self):
        trace = self.readings(96, 97, 98)

        result = detect_completed_cycle(trace)

        self.assertIsNone(result)

    def test_detect_completed_cycle_low_without_a_following_high_is_none(self):
        trace = self.readings(60, 4, 40, 55)

        result = detect_completed_cycle(trace)

        self.assertIsNone(result)

    def test_detect_completed_cycle_skips_readings_up_to_the_last_cycle(self):
        trace = self.readings(4, 96, 60, 55, 50)

        result = detect_completed_cycle(trace, after=STORED_AT + timedelta(hours=1))

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
