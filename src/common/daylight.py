"""Whether it is dark outside, worked out from the sun rather than from the clock.

A fixed evening hour is wrong for most of the year at this latitude: in Kyiv the sun sets before five in
December and after nine in June, so "after 19:00" means pitch dark in winter and full daylight in summer.

The threshold is **civil twilight** (the sun six degrees below the horizon) rather than the horizon itself,
because that is roughly the point at which a person walking into an unlit hallway wants the light on — the
sun has set a good half hour earlier and the sky is still bright.

The algorithm is the standard low-precision solar position one; it is accurate to about a minute, which is
far beyond what a decision about a light needs.
"""
import math
from datetime import datetime

CIVIL_TWILIGHT_DEGREES = -6.0


def solar_elevation_degrees(moment: datetime, latitude: float, longitude: float) -> float:
    """How high the sun stands above the horizon, negative once it has set."""
    # days since the J2000.0 epoch, in the fractional form the formulae expect
    julian_day = moment.timestamp() / 86400.0 + 2440587.5
    days = julian_day - 2451545.0

    mean_longitude = math.radians((280.460 + 0.9856474 * days) % 360)
    mean_anomaly = math.radians((357.528 + 0.9856003 * days) % 360)
    ecliptic_longitude = (
        mean_longitude + math.radians(1.915) * math.sin(mean_anomaly) + math.radians(0.020) * math.sin(2 * mean_anomaly)
    )

    obliquity = math.radians(23.439 - 0.0000004 * days)
    declination = math.asin(math.sin(obliquity) * math.sin(ecliptic_longitude))
    right_ascension = math.atan2(math.cos(obliquity) * math.sin(ecliptic_longitude), math.cos(ecliptic_longitude))

    greenwich_sidereal = math.radians((280.46061837 + 360.98564736629 * days) % 360)
    hour_angle = greenwich_sidereal + math.radians(longitude) - right_ascension

    phi = math.radians(latitude)
    elevation = math.asin(
        math.sin(phi) * math.sin(declination) + math.cos(phi) * math.cos(declination) * math.cos(hour_angle)
    )
    return math.degrees(elevation)


def is_dark(moment: datetime, latitude: float, longitude: float) -> bool:
    """True once the sun is far enough down that an unlit hallway is genuinely dark."""
    return solar_elevation_degrees(moment, latitude, longitude) < CIVIL_TWILIGHT_DEGREES
