from datetime import datetime
from enum import StrEnum

from src.common.domain import DomainModel


class AlertLevel(StrEnum):
    """
    What the official map says about one place.

    the distinction is the whole feature: a yellow drone warning runs for hours several nights a week, and
    a light that comes on for every one of them is a light nobody leaves enabled. red is the one that means
    «взуйся і йди».
    """

    NONE = "none"
    YELLOW = "yellow"
    RED = "red"


class AirAlert(DomainModel):
    """The current state for the place we live in, as the source reports it."""

    level: AlertLevel
    reason: str | None = None
    since: datetime | None = None


class AlertTransition(StrEnum):
    RAISED = "raised"
    CLEARED = "cleared"
    UNCHANGED = "unchanged"
