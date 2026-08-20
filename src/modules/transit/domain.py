from datetime import datetime
from enum import StrEnum

from src.common.domain import DomainModel


class RouteVehicleKind(StrEnum):
    TROLLEYBUS = "trolleybus"
    BUS = "bus"


class WatchedRoute(DomainModel):
    route_id: str
    short_name: str
    vehicle_kind: RouteVehicleKind


class GeoPoint(DomainModel):
    latitude: float
    longitude: float


class StopLocation(DomainModel):
    stop_id: str
    location: GeoPoint


class VehiclePosition(DomainModel):
    vehicle_id: str
    route_id: str
    location: GeoPoint
    recorded_at: datetime


class RealtimeSnapshot(DomainModel):
    # only the watched routes' vehicles; the whole feed reaches us as aggregates, never as one stale vehicle
    vehicles: list[VehiclePosition]
    total_vehicle_count: int
    latest_vehicle_recorded_at: datetime | None
    feed_timestamp: datetime
    fetched_at: datetime


class RouteShape(DomainModel):
    route_id: str
    # the ordered polyline of the direction that serves the watched stop
    points: list[GeoPoint]


class RouteArrival(DomainModel):
    route: WatchedRoute
    # None means "поки не видно" — no qualifying vehicle heading to the stop
    eta_minutes: int | None
    distance_meters: float | None


class TransitReportStatus(StrEnum):
    ARRIVALS = "arrivals"
    AIR_RAID = "air_raid"
    FEED_UNAVAILABLE = "feed_unavailable"


class TransitReport(DomainModel):
    status: TransitReportStatus
    # sorted nearest-first with the invisible routes last; empty unless status is ARRIVALS
    arrivals: list[RouteArrival] = []


def parse_watched_routes(text: str) -> tuple[WatchedRoute, ...]:
    """Parses the settings string "route_id:short_name:kind,…" so config stays plain-typed"""
    watched_routes = []
    for entry in text.split(","):
        entry = entry.strip()
        if not entry:
            continue
        route_id, short_name, kind = entry.split(":")
        watched_routes.append(
            WatchedRoute(
                route_id=route_id.strip(),
                short_name=short_name.strip(),
                vehicle_kind=RouteVehicleKind(kind.strip()),
            )
        )
    return tuple(watched_routes)
