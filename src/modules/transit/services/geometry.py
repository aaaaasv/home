import math
from typing import NamedTuple

from src.modules.transit.domain import GeoPoint

EARTH_RADIUS_METERS = 6_371_000.0


class PolylineProjection(NamedTuple):
    distance_along_meters: float
    offset_meters: float


def haversine_meters(first: GeoPoint, second: GeoPoint) -> float:
    """Great-circle distance between two coordinates in metres"""
    first_latitude = math.radians(first.latitude)
    second_latitude = math.radians(second.latitude)
    latitude_delta = math.radians(second.latitude - first.latitude)
    longitude_delta = math.radians(second.longitude - first.longitude)
    central_angle = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(first_latitude) * math.cos(second_latitude) * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(central_angle))


def cumulative_distances(points: list[GeoPoint]) -> list[float]:
    """Running distance from the first point to each point along the polyline"""
    distances = [0.0]
    for previous, current in zip(points, points[1:]):
        distances.append(distances[-1] + haversine_meters(previous, current))
    return distances


def project_onto_polyline(point: GeoPoint, points: list[GeoPoint], cumulative: list[float]) -> PolylineProjection:
    """The nearest point on the polyline: how far along it lies and how far off the line the query point is"""
    if len(points) < 2:
        return PolylineProjection(distance_along_meters=0.0, offset_meters=haversine_meters(point, points[0]))

    best: PolylineProjection | None = None
    for index in range(len(points) - 1):
        segment_start = points[index]
        segment_end = points[index + 1]
        fraction, offset_meters = _project_onto_segment(point, segment_start, segment_end)
        segment_length = cumulative[index + 1] - cumulative[index]
        distance_along_meters = cumulative[index] + fraction * segment_length
        if best is None or offset_meters < best.offset_meters:
            best = PolylineProjection(distance_along_meters=distance_along_meters, offset_meters=offset_meters)
    return best


def _project_onto_segment(point: GeoPoint, segment_start: GeoPoint, segment_end: GeoPoint) -> tuple[float, float]:
    """The clamped fraction along the segment and the perpendicular offset, in a local planar frame around the start"""
    point_x, point_y = _to_local_meters(point, segment_start)
    end_x, end_y = _to_local_meters(segment_end, segment_start)
    segment_length_squared = end_x**2 + end_y**2
    if segment_length_squared == 0:
        fraction = 0.0
    else:
        fraction = (point_x * end_x + point_y * end_y) / segment_length_squared
        fraction = max(0.0, min(1.0, fraction))
    closest_x = fraction * end_x
    closest_y = fraction * end_y
    offset_meters = math.hypot(point_x - closest_x, point_y - closest_y)
    return fraction, offset_meters


def _to_local_meters(point: GeoPoint, origin: GeoPoint) -> tuple[float, float]:
    # equirectangular projection around the origin — exact enough at city scale, avoids a full geodesic solver
    origin_latitude = math.radians(origin.latitude)
    x = EARTH_RADIUS_METERS * math.radians(point.longitude - origin.longitude) * math.cos(origin_latitude)
    y = EARTH_RADIUS_METERS * math.radians(point.latitude - origin.latitude)
    return x, y
