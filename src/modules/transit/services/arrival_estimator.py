from datetime import datetime
from typing import NamedTuple

from src.modules.transit.domain import (
    GeoPoint,
    RealtimeSnapshot,
    RouteArrival,
    RouteShape,
    StopLocation,
    VehiclePosition,
    WatchedRoute,
)
from src.modules.transit.services.geometry import cumulative_distances, haversine_meters, project_onto_polyline
from src.modules.transit.services.position_sanity import is_inside_kyiv, is_plausible_movement

# ~20 km/h — the fallback speed for a first sighting on a shaped route, self-corrects once tracking has two fixes
ASSUMED_SPEED_METERS_PER_SECOND = 5.5
# a vehicle farther than this off the route line is on a different street, not on this route
MAXIMUM_SHAPE_OFFSET_METERS = 80.0
SECONDS_PER_MINUTE = 60


class VehicleObservation(NamedTuple):
    """One vehicle's fix from the previous poll, so the next poll can measure its progress toward the stop"""

    location: GeoPoint
    recorded_at: datetime
    distance_to_stop_meters: float


class ArrivalEstimator:
    """The D-hybrid: shape-projected eta where geometry exists, approach-tracked straight-line where it does not"""

    def __init__(self, stop: StopLocation, watched_routes: tuple[WatchedRoute, ...]):
        self.stop = stop
        self.watched_routes = watched_routes
        self._route_by_id = {route.route_id: route for route in watched_routes}
        # progress tracking survives across polls, so a shared long-lived estimator is threaded everywhere
        self._previous_observations: dict[str, VehicleObservation] = {}

    def estimate(self, snapshot: RealtimeSnapshot, shapes: dict[str, RouteShape]) -> list[RouteArrival]:
        fresh_observations: dict[str, VehicleObservation] = {}
        best_arrival_by_route: dict[str, RouteArrival] = {}

        for vehicle in snapshot.vehicles:
            route = self._route_by_id.get(vehicle.route_id)
            if route is None:
                continue
            if not is_inside_kyiv(vehicle.location):
                continue
            previous = self._previous_observations.get(vehicle.vehicle_id)
            if previous is not None and not self._is_plausible(previous, vehicle):
                continue

            shape = shapes.get(vehicle.route_id)
            if shape is not None:
                arrival, observation = self._estimate_with_shape(vehicle, route, shape, previous)
            else:
                arrival, observation = self._estimate_straight_line(vehicle, route, previous)

            if observation is not None:
                fresh_observations[vehicle.vehicle_id] = observation
            if arrival is not None:
                existing = best_arrival_by_route.get(route.route_id)
                if existing is None or arrival.eta_minutes < existing.eta_minutes:
                    best_arrival_by_route[route.route_id] = arrival

        self._previous_observations = fresh_observations
        return self._ordered_arrivals(best_arrival_by_route)

    def _is_plausible(self, previous: VehicleObservation, vehicle: VehiclePosition) -> bool:
        elapsed_seconds = (vehicle.recorded_at - previous.recorded_at).total_seconds()
        return is_plausible_movement(previous.location, vehicle.location, elapsed_seconds)

    def _estimate_with_shape(
        self, vehicle: VehiclePosition, route: WatchedRoute, shape: RouteShape, previous: VehicleObservation | None
    ) -> tuple[RouteArrival | None, VehicleObservation | None]:
        cumulative = cumulative_distances(shape.points)
        vehicle_projection = project_onto_polyline(vehicle.location, shape.points, cumulative)
        if vehicle_projection.offset_meters > MAXIMUM_SHAPE_OFFSET_METERS:
            return None, None

        stop_projection = project_onto_polyline(self.stop.location, shape.points, cumulative)
        remaining_meters = stop_projection.distance_along_meters - vehicle_projection.distance_along_meters
        observation = VehicleObservation(
            location=vehicle.location,
            recorded_at=vehicle.recorded_at,
            distance_to_stop_meters=remaining_meters,
        )
        if remaining_meters <= 0:
            # already past the stop toward the centre — keep tracking, but it will not arrive here
            return None, observation

        speed = self._closing_speed(previous, observation)
        if speed is None:
            # a first sighting has no measured speed; the shape already fixes the direction, so show it at the
            # assumed pace and let the next tick correct it
            speed = ASSUMED_SPEED_METERS_PER_SECOND
        elif speed <= 0:
            # measured as moving away along the line — the opposite carriageway, or already departing the stop
            return None, observation
        arrival = RouteArrival(
            route=route,
            eta_minutes=_to_eta_minutes(remaining_meters, speed),
            distance_meters=remaining_meters,
        )
        return arrival, observation

    def _estimate_straight_line(
        self, vehicle: VehiclePosition, route: WatchedRoute, previous: VehicleObservation | None
    ) -> tuple[RouteArrival | None, VehicleObservation | None]:
        distance_meters = haversine_meters(vehicle.location, self.stop.location)
        observation = VehicleObservation(
            location=vehicle.location,
            recorded_at=vehicle.recorded_at,
            distance_to_stop_meters=distance_meters,
        )

        closing_speed = self._closing_speed(previous, observation)
        if closing_speed is None or closing_speed <= 0:
            # a first sighting has no direction, and a receding vehicle is not heading here
            return None, observation
        arrival = RouteArrival(
            route=route,
            eta_minutes=_to_eta_minutes(distance_meters, closing_speed),
            distance_meters=distance_meters,
        )
        return arrival, observation

    def _closing_speed(self, previous: VehicleObservation | None, current: VehicleObservation) -> float | None:
        if previous is None:
            return None
        elapsed_seconds = (current.recorded_at - previous.recorded_at).total_seconds()
        if elapsed_seconds <= 0:
            return None
        return (previous.distance_to_stop_meters - current.distance_to_stop_meters) / elapsed_seconds

    def _ordered_arrivals(self, best_arrival_by_route: dict[str, RouteArrival]) -> list[RouteArrival]:
        arrivals = [
            best_arrival_by_route.get(route.route_id, RouteArrival(route=route, eta_minutes=None, distance_meters=None))
            for route in self.watched_routes
        ]
        arrivals.sort(key=_sort_key)
        return arrivals


def _to_eta_minutes(distance_meters: float, speed_meters_per_second: float) -> int:
    return max(1, round(distance_meters / speed_meters_per_second / SECONDS_PER_MINUTE))


def _sort_key(arrival: RouteArrival) -> tuple[bool, int]:
    # nearest eta first, the invisible routes (no qualifying vehicle) last
    if arrival.eta_minutes is None:
        return True, 0
    return False, arrival.eta_minutes
