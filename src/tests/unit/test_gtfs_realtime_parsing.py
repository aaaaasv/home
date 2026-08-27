import unittest
from datetime import datetime, timezone

from google.transit import gtfs_realtime_pb2

from src.infrastructure.adapters.gtfs_realtime_feed import parse_realtime_snapshot

WATCHED_ROUTE_IDS = frozenset({"2_30", "3_127"})
FETCHED_AT = datetime(2026, 8, 13, 9, 0, 30, tzinfo=timezone.utc)
FEED_TIMESTAMP_POSIX = 1_786_611_600  # 2026-08-13 09:00:00 UTC


def add_vehicle(
    feed: gtfs_realtime_pb2.FeedMessage,
    entity_id: str,
    vehicle_id: str,
    route_id: str,
    latitude: float,
    longitude: float,
    timestamp: int,
) -> None:
    entity = feed.entity.add()
    entity.id = entity_id
    entity.vehicle.vehicle.id = vehicle_id
    entity.vehicle.trip.route_id = route_id
    entity.vehicle.position.latitude = latitude
    entity.vehicle.position.longitude = longitude
    entity.vehicle.timestamp = timestamp


def build_feed_payload() -> bytes:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = FEED_TIMESTAMP_POSIX
    add_vehicle(feed, "e1", "veh_3", "2_30", 50.44, 30.49, FEED_TIMESTAMP_POSIX - 10)
    add_vehicle(feed, "e2", "veh_69", "3_127", 50.45, 30.51, FEED_TIMESTAMP_POSIX - 40)
    add_vehicle(feed, "e3", "veh_other", "9_99", 50.46, 30.52, FEED_TIMESTAMP_POSIX - 5)
    return feed.SerializeToString()


class ParseRealtimeSnapshotTestCase(unittest.TestCase):
    def setUp(self):
        self.snapshot = parse_realtime_snapshot(build_feed_payload(), WATCHED_ROUTE_IDS, FETCHED_AT)

    def test_parse_snapshot_keeps_only_watched_route_vehicles(self):
        self.assertEqual([vehicle.vehicle_id for vehicle in self.snapshot.vehicles], ["veh_3", "veh_69"])
        self.assertEqual([vehicle.route_id for vehicle in self.snapshot.vehicles], ["2_30", "3_127"])

    def test_parse_snapshot_reads_watched_vehicle_position_and_time(self):
        first_vehicle = self.snapshot.vehicles[0]

        # gtfs-realtime stores positions as single-precision floats, so compare within that tolerance
        self.assertAlmostEqual(first_vehicle.location.latitude, 50.44, places=5)
        self.assertAlmostEqual(first_vehicle.location.longitude, 30.49, places=5)
        self.assertEqual(first_vehicle.recorded_at, datetime(2026, 8, 13, 8, 59, 50, tzinfo=timezone.utc))

    def test_parse_snapshot_counts_the_whole_fleet_including_unwatched(self):
        self.assertEqual(self.snapshot.total_vehicle_count, 3)

    def test_parse_snapshot_takes_the_latest_recorded_time_across_the_whole_feed(self):
        # the freshest is the unwatched vehicle at feed_timestamp - 5 s, still counted for the aggregate
        self.assertEqual(
            self.snapshot.latest_vehicle_recorded_at, datetime(2026, 8, 13, 8, 59, 55, tzinfo=timezone.utc)
        )

    def test_parse_snapshot_reads_feed_timestamp_and_carries_fetched_at(self):
        self.assertEqual(self.snapshot.feed_timestamp, datetime(2026, 8, 13, 9, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(self.snapshot.fetched_at, FETCHED_AT)


if __name__ == "__main__":
    unittest.main()
