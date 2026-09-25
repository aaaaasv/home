from datetime import datetime
from enum import StrEnum

from src.common.domain import DomainModel


class ThreatKind(StrEnum):
    """What the tracker calls the thing — anything it has not taught us maps to UNKNOWN rather than crashing."""

    UAV = "uav"
    FPV = "fpv"
    MISSILE = "missile"
    BALLISTIC = "ballistic"
    KAB = "kab"
    AIRCRAFT = "aircraft"
    UNKNOWN = "unknown"


class ThreatConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AirThreat(DomainModel):
    """
    One tracked object, as the map sees it: an estimated position now, not a destination.

    checked against reference coordinates 25.09.2026 — a track named «Кременчук» sat 10.6 km from the city
    centre, so `latitude`/`longitude` is where the thing is believed to be and `locality` is the nearest name.
    `heading` is missing often enough that nothing may depend on having it.
    """

    tracker_id: str
    kind: ThreatKind
    title: str
    locality: str | None
    region: str | None
    latitude: float
    longitude: float
    heading_degrees: float | None
    confidence: ThreatConfidence
    source_count: int
    uncertainty_kilometres: float | None
    is_position_confirmed: bool
    updated_at: datetime


class ApproachingThreat(DomainModel):
    """A threat that earned a message, with what the map cannot know: how far, how soon, and whether at us."""

    threat: AirThreat
    distance_kilometres: float
    is_inbound: bool
    # how long it would take to reach us at this kind's usual speed — None when it is not coming our way
    minutes_away: float | None = None


class AirThreatChanges(DomainModel):
    """What the household has not been told yet, what it has, and what has faded from the map."""

    appeared: list[ApproachingThreat]
    standing: list[ApproachingThreat]
    gone: list[str]
