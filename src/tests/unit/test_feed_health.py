import unittest
from datetime import datetime, timedelta, timezone

from src.modules.transit.domain import RealtimeSnapshot
from src.modules.transit.services.feed_health import is_feed_trustworthy

NOW = datetime(2026, 8, 13, 9, 0, 0, tzinfo=timezone.utc)


def build_snapshot(
    feed_age_seconds: int = 5,
    latest_vehicle_age_seconds: int = 20,
    total_vehicle_count: int = 460,
) -> RealtimeSnapshot:
    return RealtimeSnapshot(
        vehicles=[],
        total_vehicle_count=total_vehicle_count,
        latest_vehicle_recorded_at=NOW - timedelta(seconds=latest_vehicle_age_seconds),
        feed_timestamp=NOW - timedelta(seconds=feed_age_seconds),
        fetched_at=NOW,
    )


class FeedHealthTestCase(unittest.TestCase):
    def test_is_feed_trustworthy_for_a_healthy_snapshot_is_true(self):
        trustworthy = is_feed_trustworthy(build_snapshot(), NOW)

        self.assertTrue(trustworthy)

    def test_is_feed_trustworthy_for_a_missing_snapshot_is_false(self):
        trustworthy = is_feed_trustworthy(None, NOW)

        self.assertFalse(trustworthy)

    def test_is_feed_trustworthy_with_a_stale_feed_timestamp_is_false(self):
        trustworthy = is_feed_trustworthy(build_snapshot(feed_age_seconds=121), NOW)

        self.assertFalse(trustworthy)

    def test_is_feed_trustworthy_with_a_collapsed_fleet_is_false(self):
        trustworthy = is_feed_trustworthy(build_snapshot(total_vehicle_count=49), NOW)

        self.assertFalse(trustworthy)

    def test_is_feed_trustworthy_with_the_whole_fleet_stale_is_false(self):
        trustworthy = is_feed_trustworthy(build_snapshot(latest_vehicle_age_seconds=181), NOW)

        self.assertFalse(trustworthy)

    def test_is_feed_trustworthy_with_no_vehicle_timestamp_is_false(self):
        snapshot = build_snapshot().model_copy(update={"latest_vehicle_recorded_at": None})

        trustworthy = is_feed_trustworthy(snapshot, NOW)

        self.assertFalse(trustworthy)

    def test_is_feed_trustworthy_with_one_stale_vehicle_in_a_fresh_fleet_stays_true(self):
        # the freshest vehicle is only 20 s old; a single 5-min-old vehicle never drags the aggregate down
        snapshot = build_snapshot(latest_vehicle_age_seconds=20, total_vehicle_count=460)

        trustworthy = is_feed_trustworthy(snapshot, NOW)

        self.assertTrue(trustworthy)


if __name__ == "__main__":
    unittest.main()
