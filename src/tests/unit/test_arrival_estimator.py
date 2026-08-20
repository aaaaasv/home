import unittest
from datetime import datetime, timedelta, timezone

from src.modules.transit.domain import (
    GeoPoint,
    RealtimeSnapshot,
    RouteShape,
    RouteVehicleKind,
    StopLocation,
    VehiclePosition,
    WatchedRoute,
)
from src.modules.transit.services.arrival_estimator import ArrivalEstimator

STOP = StopLocation(stop_id="1_100", location=GeoPoint(latitude=50.45, longitude=30.49))
ROUTE_3 = WatchedRoute(route_id="2_30", short_name="3", vehicle_kind=RouteVehicleKind.TROLLEYBUS)
ROUTE_9K = WatchedRoute(route_id="2_842", short_name="9К", vehicle_kind=RouteVehicleKind.TROLLEYBUS)
ROUTE_69 = WatchedRoute(route_id="3_127", short_name="69", vehicle_kind=RouteVehicleKind.BUS)

# a straight south-to-north meridian at longitude 30.49; the stop at 50.45 sits ~5560 m along it
MERIDIAN = [GeoPoint(latitude=50.40, longitude=30.49), GeoPoint(latitude=50.46, longitude=30.49)]
SHAPED_ROUTE_3 = {"2_30": RouteShape(route_id="2_30", points=MERIDIAN)}

POLL_TIME = datetime(2026, 8, 13, 9, 0, 0, tzinfo=timezone.utc)
NEXT_POLL_TIME = POLL_TIME + timedelta(seconds=120)


def build_snapshot(vehicles: list[VehiclePosition], recorded_at: datetime) -> RealtimeSnapshot:
    return RealtimeSnapshot(
        vehicles=vehicles,
        total_vehicle_count=460,
        latest_vehicle_recorded_at=recorded_at,
        feed_timestamp=recorded_at,
        fetched_at=recorded_at,
    )


def build_vehicle(vehicle_id: str, route_id: str, latitude: float, longitude: float, recorded_at: datetime):
    return VehiclePosition(
        vehicle_id=vehicle_id,
        route_id=route_id,
        location=GeoPoint(latitude=latitude, longitude=longitude),
        recorded_at=recorded_at,
    )


def arrival_for(arrivals, short_name: str):
    return next(arrival for arrival in arrivals if arrival.route.short_name == short_name)


class ShapedRouteEstimateTestCase(unittest.TestCase):
    def test_estimate_on_a_shape_first_sighting_falls_back_to_the_assumed_speed(self):
        estimator = ArrivalEstimator(stop=STOP, watched_routes=(ROUTE_3,))
        vehicle = build_vehicle("v1", "2_30", 50.42, 30.49, POLL_TIME)

        arrivals = estimator.estimate(build_snapshot([vehicle], POLL_TIME), SHAPED_ROUTE_3)

        arrival = arrival_for(arrivals, "3")
        self.assertEqual(arrival.eta_minutes, 10)
        self.assertEqual(round(arrival.distance_meters), 3336)

    def test_estimate_on_a_shape_second_poll_uses_the_tracked_speed(self):
        estimator = ArrivalEstimator(stop=STOP, watched_routes=(ROUTE_3,))
        estimator.estimate(
            build_snapshot([build_vehicle("v1", "2_30", 50.42, 30.49, POLL_TIME)], POLL_TIME), SHAPED_ROUTE_3
        )

        arrivals = estimator.estimate(
            build_snapshot([build_vehicle("v1", "2_30", 50.43, 30.49, NEXT_POLL_TIME)], NEXT_POLL_TIME),
            SHAPED_ROUTE_3,
        )

        arrival = arrival_for(arrivals, "3")
        self.assertEqual(arrival.eta_minutes, 4)
        self.assertEqual(round(arrival.distance_meters), 2224)

    def test_estimate_on_a_shape_hides_a_vehicle_past_the_stop(self):
        estimator = ArrivalEstimator(stop=STOP, watched_routes=(ROUTE_3,))
        vehicle_past_the_stop = build_vehicle("v1", "2_30", 50.47, 30.49, POLL_TIME)

        arrivals = estimator.estimate(build_snapshot([vehicle_past_the_stop], POLL_TIME), SHAPED_ROUTE_3)

        self.assertIsNone(arrival_for(arrivals, "3").eta_minutes)

    def test_estimate_on_a_shape_hides_a_vehicle_far_off_the_route(self):
        estimator = ArrivalEstimator(stop=STOP, watched_routes=(ROUTE_3,))
        # 0.0015° of longitude off the line is ~106 m, beyond the 80 m on-route tolerance
        vehicle_off_the_route = build_vehicle("v1", "2_30", 50.42, 30.0915, POLL_TIME)

        arrivals = estimator.estimate(build_snapshot([vehicle_off_the_route], POLL_TIME), SHAPED_ROUTE_3)

        self.assertIsNone(arrival_for(arrivals, "3").eta_minutes)

    def test_estimate_on_a_shape_hides_a_vehicle_receding_along_the_route(self):
        estimator = ArrivalEstimator(stop=STOP, watched_routes=(ROUTE_3,))
        estimator.estimate(
            build_snapshot([build_vehicle("v1", "2_30", 50.43, 30.49, POLL_TIME)], POLL_TIME), SHAPED_ROUTE_3
        )

        arrivals = estimator.estimate(
            build_snapshot([build_vehicle("v1", "2_30", 50.42, 30.49, NEXT_POLL_TIME)], NEXT_POLL_TIME),
            SHAPED_ROUTE_3,
        )

        self.assertIsNone(arrival_for(arrivals, "3").eta_minutes)


class StraightLineEstimateTestCase(unittest.TestCase):
    def test_estimate_without_a_shape_hides_a_first_sighting(self):
        estimator = ArrivalEstimator(stop=STOP, watched_routes=(ROUTE_9K,))
        vehicle = build_vehicle("w1", "2_842", 50.42, 30.49, POLL_TIME)

        arrivals = estimator.estimate(build_snapshot([vehicle], POLL_TIME), {})

        self.assertIsNone(arrival_for(arrivals, "9К").eta_minutes)

    def test_estimate_without_a_shape_shows_a_vehicle_approaching_the_stop(self):
        estimator = ArrivalEstimator(stop=STOP, watched_routes=(ROUTE_9K,))
        estimator.estimate(build_snapshot([build_vehicle("w1", "2_842", 50.42, 30.49, POLL_TIME)], POLL_TIME), {})

        arrivals = estimator.estimate(
            build_snapshot([build_vehicle("w1", "2_842", 50.43, 30.49, NEXT_POLL_TIME)], NEXT_POLL_TIME), {}
        )

        arrival = arrival_for(arrivals, "9К")
        self.assertEqual(arrival.eta_minutes, 4)
        self.assertEqual(round(arrival.distance_meters), 2224)

    def test_estimate_without_a_shape_hides_a_receding_vehicle(self):
        estimator = ArrivalEstimator(stop=STOP, watched_routes=(ROUTE_9K,))
        estimator.estimate(build_snapshot([build_vehicle("w2", "2_842", 50.43, 30.49, POLL_TIME)], POLL_TIME), {})

        arrivals = estimator.estimate(
            build_snapshot([build_vehicle("w2", "2_842", 50.42, 30.49, NEXT_POLL_TIME)], NEXT_POLL_TIME), {}
        )

        self.assertIsNone(arrival_for(arrivals, "9К").eta_minutes)


class PositionSanityEstimateTestCase(unittest.TestCase):
    def test_estimate_discards_a_teleporting_vehicle(self):
        estimator = ArrivalEstimator(stop=STOP, watched_routes=(ROUTE_9K,))
        estimator.estimate(build_snapshot([build_vehicle("w3", "2_842", 50.44, 30.49, POLL_TIME)], POLL_TIME), {})

        arrivals = estimator.estimate(
            build_snapshot([build_vehicle("w3", "2_842", 50.30, 30.49, NEXT_POLL_TIME)], NEXT_POLL_TIME), {}
        )

        self.assertIsNone(arrival_for(arrivals, "9К").eta_minutes)

    def test_estimate_discards_a_fix_outside_kyiv(self):
        estimator = ArrivalEstimator(stop=STOP, watched_routes=(ROUTE_9K,))
        vehicle_outside_kyiv = build_vehicle("w4", "2_842", 49.0, 30.49, POLL_TIME)

        arrivals = estimator.estimate(build_snapshot([vehicle_outside_kyiv], POLL_TIME), {})

        self.assertIsNone(arrival_for(arrivals, "9К").eta_minutes)


class ArrivalOrderingTestCase(unittest.TestCase):
    def test_estimate_returns_routes_nearest_first_with_invisible_routes_last(self):
        estimator = ArrivalEstimator(stop=STOP, watched_routes=(ROUTE_3, ROUTE_9K, ROUTE_69))
        shapes = {
            "2_30": RouteShape(route_id="2_30", points=MERIDIAN),
            "3_127": RouteShape(route_id="3_127", points=MERIDIAN),
        }
        vehicles = [
            build_vehicle("a", "2_30", 50.42, 30.49, POLL_TIME),
            build_vehicle("b", "3_127", 50.44, 30.49, POLL_TIME),
        ]

        arrivals = estimator.estimate(build_snapshot(vehicles, POLL_TIME), shapes)

        self.assertEqual([arrival.route.short_name for arrival in arrivals], ["69", "3", "9К"])
        self.assertEqual([arrival.eta_minutes for arrival in arrivals], [3, 10, None])


if __name__ == "__main__":
    unittest.main()
