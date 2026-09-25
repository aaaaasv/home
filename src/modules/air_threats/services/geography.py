"""The two numbers the threat map cannot supply, because it does not know where we live.

Everything here is plain trigonometry on a sphere and deliberately has no dependencies: it is the one part
of this module that must be provably right, since a wrong bearing turns "flying away" into "flying at us".
"""
import math

EARTH_RADIUS_KILOMETRES = 6371.0


def distance_kilometres(
    first_latitude: float, first_longitude: float, second_latitude: float, second_longitude: float
) -> float:
    """Great-circle distance — haversine, which stays accurate at the short ranges this module cares about."""
    first_phi = math.radians(first_latitude)
    second_phi = math.radians(second_latitude)
    delta_phi = math.radians(second_latitude - first_latitude)
    delta_lambda = math.radians(second_longitude - first_longitude)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(first_phi) * math.cos(second_phi) * math.sin(delta_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KILOMETRES * math.asin(math.sqrt(a))


def bearing_degrees(from_latitude: float, from_longitude: float, to_latitude: float, to_longitude: float) -> float:
    """Initial compass bearing from one point to another, 0° north and growing clockwise."""
    from_phi = math.radians(from_latitude)
    to_phi = math.radians(to_latitude)
    delta_lambda = math.radians(to_longitude - from_longitude)

    x = math.sin(delta_lambda) * math.cos(to_phi)
    y = math.cos(from_phi) * math.sin(to_phi) - math.sin(from_phi) * math.cos(to_phi) * math.cos(delta_lambda)
    return math.degrees(math.atan2(x, y)) % 360


def angle_between_degrees(first: float, second: float) -> float:
    """The shorter way round between two compass bearings, always 0–180."""
    difference = abs(first - second) % 360
    return 360 - difference if difference > 180 else difference


def compass_point(bearing: float) -> str:
    """Which way it lies from us, in the words a person uses rather than in degrees."""
    points = (
        "півночі",
        "північного сходу",
        "сходу",
        "південного сходу",
        "півдня",
        "південного заходу",
        "заходу",
        "північного заходу",
    )
    return points[round(bearing % 360 / 45) % 8]
