import unittest
from datetime import datetime, timedelta, timezone

from src.modules.transit.domain import (
    GeoPoint,
    RealtimeSnapshot,
    RouteArrival,
    RouteShape,
    RouteVehicleKind,
    TransitReportStatus,
    WatchedRoute,
)
from src.modules.transit.use_cases.compose_transit_report import ComposeTransitReportUseCase
from src.tests.fakes import FixedAirRaidAlertSource, FixedRealtimeFeed, FixedRouteShapeCatalog

# a fixed "now" keeps every staleness assertion exact rather than relative to the wall clock
FROZEN_NOW = datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)

TROLLEYBUS_3 = WatchedRoute(route_id="2_30", short_name="3", vehicle_kind=RouteVehicleKind.TROLLEYBUS)
TROLLEYBUS_9K = WatchedRoute(route_id="2_842", short_name="9К", vehicle_kind=RouteVehicleKind.TROLLEYBUS)
BUS_69 = WatchedRoute(route_id="3_127", short_name="69", vehicle_kind=RouteVehicleKind.BUS)
WATCHED_ROUTES = (TROLLEYBUS_3, TROLLEYBUS_9K, BUS_69)


def build_snapshot(
    total_vehicle_count: int = 460,
    feed_timestamp: datetime = FROZEN_NOW,
    latest_vehicle_recorded_at: datetime | None = None,
) -> RealtimeSnapshot:
    return RealtimeSnapshot(
        vehicles=[],
        total_vehicle_count=total_vehicle_count,
        latest_vehicle_recorded_at=latest_vehicle_recorded_at or FROZEN_NOW - timedelta(seconds=30),
        feed_timestamp=feed_timestamp,
        fetched_at=FROZEN_NOW,
    )


class StubArrivalEstimator:
    """A canned estimator so these tests exercise the guard orchestration, not track A's geometry"""

    def __init__(self, arrivals: list[RouteArrival]):
        self.arrivals = arrivals
        self.received_snapshot: RealtimeSnapshot | None = None
        self.received_shapes: dict[str, RouteShape] | None = None

    def estimate(self, snapshot: RealtimeSnapshot, shapes: dict[str, RouteShape]) -> list[RouteArrival]:
        self.received_snapshot = snapshot
        self.received_shapes = shapes
        return self.arrivals


class ComposeTransitReportTestCase(unittest.IsolatedAsyncioTestCase):
    def compose(
        self,
        alert_active: bool | None,
        snapshot: RealtimeSnapshot | None,
        estimator: StubArrivalEstimator,
        catalog: FixedRouteShapeCatalog | None = None,
    ) -> ComposeTransitReportUseCase:
        self.realtime_feed = FixedRealtimeFeed(snapshot)
        return ComposeTransitReportUseCase(
            realtime_feed=self.realtime_feed,
            shape_catalog=catalog or FixedRouteShapeCatalog(),
            arrival_estimator=estimator,
            air_raid_alert_source=FixedAirRaidAlertSource(alert_active),
            watched_routes=WATCHED_ROUTES,
            clock=lambda: FROZEN_NOW,
        )

    async def test_compose_report_with_an_active_alert_returns_air_raid_and_skips_the_feed(self):
        estimator = StubArrivalEstimator([])
        use_case = self.compose(alert_active=True, snapshot=build_snapshot(), estimator=estimator)

        report = await use_case()

        self.assertEqual(report.status, TransitReportStatus.AIR_RAID)
        self.assertEqual(report.arrivals, [])
        self.assertEqual(self.realtime_feed.fetch_calls, 0)
        self.assertIsNone(estimator.received_snapshot)

    async def test_compose_report_with_an_unreachable_feed_returns_feed_unavailable(self):
        estimator = StubArrivalEstimator([])
        use_case = self.compose(alert_active=None, snapshot=None, estimator=estimator)

        report = await use_case()

        self.assertEqual(report.status, TransitReportStatus.FEED_UNAVAILABLE)
        self.assertEqual(report.arrivals, [])
        self.assertIsNone(estimator.received_snapshot)

    async def test_compose_report_with_a_stale_feed_timestamp_returns_feed_unavailable(self):
        estimator = StubArrivalEstimator([])
        stale_snapshot = build_snapshot(feed_timestamp=FROZEN_NOW - timedelta(seconds=200))
        use_case = self.compose(alert_active=None, snapshot=stale_snapshot, estimator=estimator)

        report = await use_case()

        self.assertEqual(report.status, TransitReportStatus.FEED_UNAVAILABLE)
        self.assertIsNone(estimator.received_snapshot)

    async def test_compose_report_with_a_collapsed_fleet_returns_feed_unavailable(self):
        estimator = StubArrivalEstimator([])
        collapsed_snapshot = build_snapshot(total_vehicle_count=10)
        use_case = self.compose(alert_active=None, snapshot=collapsed_snapshot, estimator=estimator)

        report = await use_case()

        self.assertEqual(report.status, TransitReportStatus.FEED_UNAVAILABLE)
        self.assertIsNone(estimator.received_snapshot)

    async def test_compose_report_with_an_unknown_alert_status_estimates_arrivals(self):
        arrivals = [RouteArrival(route=TROLLEYBUS_3, eta_minutes=4, distance_meters=1100.0)]
        estimator = StubArrivalEstimator(arrivals)
        snapshot = build_snapshot()
        use_case = self.compose(alert_active=None, snapshot=snapshot, estimator=estimator)

        report = await use_case()

        self.assertEqual(report.status, TransitReportStatus.ARRIVALS)
        self.assertEqual(report.arrivals, arrivals)
        self.assertEqual(estimator.received_snapshot, snapshot)

    async def test_compose_report_with_a_healthy_feed_returns_arrivals_nearest_first_and_invisible_last(self):
        ordered_arrivals = [
            RouteArrival(route=TROLLEYBUS_3, eta_minutes=4, distance_meters=1100.0),
            RouteArrival(route=BUS_69, eta_minutes=9, distance_meters=2600.0),
            RouteArrival(route=TROLLEYBUS_9K, eta_minutes=None, distance_meters=None),
        ]
        estimator = StubArrivalEstimator(ordered_arrivals)
        use_case = self.compose(alert_active=None, snapshot=build_snapshot(), estimator=estimator)

        report = await use_case()

        self.assertEqual(report.status, TransitReportStatus.ARRIVALS)
        self.assertEqual(report.arrivals, ordered_arrivals)

    async def test_compose_report_with_a_missing_shape_degrades_that_route_to_straight_line(self):
        shape_for_3 = RouteShape(route_id="2_30", points=[GeoPoint(latitude=50.44, longitude=30.49)])
        shape_for_69 = RouteShape(route_id="3_127", points=[GeoPoint(latitude=50.45, longitude=30.50)])
        catalog = FixedRouteShapeCatalog({"2_30": shape_for_3, "3_127": shape_for_69})
        estimator = StubArrivalEstimator([RouteArrival(route=BUS_69, eta_minutes=9, distance_meters=2600.0)])
        use_case = self.compose(alert_active=None, snapshot=build_snapshot(), estimator=estimator, catalog=catalog)

        report = await use_case()

        self.assertEqual(report.status, TransitReportStatus.ARRIVALS)
        self.assertEqual(estimator.received_shapes, {"2_30": shape_for_3, "3_127": shape_for_69})


if __name__ == "__main__":
    unittest.main()
