from src.modules.transit.domain import GeoPoint
from src.modules.transit.services.geometry import haversine_meters

# a generous bounding box around Kyiv — a jammed fix lands far outside it, a real vehicle never does
KYIV_MINIMUM_LATITUDE = 50.2
KYIV_MAXIMUM_LATITUDE = 50.6
KYIV_MINIMUM_LONGITUDE = 30.2
KYIV_MAXIMUM_LONGITUDE = 30.85

# ~90 km/h — above any trolleybus or bus, so a fix that implies more speed is a teleport, not motion
MAXIMUM_PLAUSIBLE_SPEED_METERS_PER_SECOND = 25


def is_inside_kyiv(location: GeoPoint) -> bool:
    return (
        KYIV_MINIMUM_LATITUDE <= location.latitude <= KYIV_MAXIMUM_LATITUDE
        and KYIV_MINIMUM_LONGITUDE <= location.longitude <= KYIV_MAXIMUM_LONGITUDE
    )


def is_plausible_movement(previous: GeoPoint, current: GeoPoint, elapsed_seconds: float) -> bool:
    """Whether the jump between two fixes is reachable at street speed — a teleport means GPS jamming"""
    if elapsed_seconds <= 0:
        # without elapsed time there is no speed to judge, so accept the fix
        return True
    return haversine_meters(previous, current) <= MAXIMUM_PLAUSIBLE_SPEED_METERS_PER_SECOND * elapsed_seconds
