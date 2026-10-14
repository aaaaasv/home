"""The alert card: what it says when it goes up, and what it says written over afterwards."""
from datetime import datetime

from src.bot.formatting import format_span
from src.bot.handlers.air_alert.messages import (
    AIR_ALERT_ALL_CLEAR,
    AIR_ALERT_LASTED,
    AIR_ALERT_LOWERED,
    AIR_ALERT_RAISED,
    AIR_ALERT_SINCE,
)
from src.common.household_calendar import HouseholdCalendar
from src.modules.air_alert.domain import AirAlert, AlertLevel


def render_alert_raised(alert: AirAlert | None, raised_at: datetime, calendar: HouseholdCalendar) -> str:
    """
    Three lines at most: what it is, why the feed says so, and since when.

    the reason comes from the feed as a whole sentence («Ракетна загроза (червоний рівень)»), so it is
    quoted rather than rebuilt — and an alert the feed gave no reason for is still worth the push.
    """
    lines = [AIR_ALERT_RAISED]
    if alert is not None and alert.reason:
        lines.append(alert.reason)
    lines.append(AIR_ALERT_SINCE.format(time=f"{calendar.local_time(raised_at):%H:%M}"))
    return "\n\n".join(lines)


def render_alert_lowered(
    alert: AirAlert | None, raised_at: datetime, lowered_at: datetime, calendar: HouseholdCalendar
) -> str:
    """
    Written over the card that pinged, because what is left behind is the half that decides anything.

    the drone warning that was running under the red is still running after it, and this is the one place
    anybody reads the end of an alert — so it names what remains instead of implying there is nothing.
    """
    remains = alert is not None and alert.level is not AlertLevel.NONE
    lines = [AIR_ALERT_LOWERED if remains else AIR_ALERT_ALL_CLEAR]
    if remains and alert.reason:
        lines.append(alert.reason)
    lines.append(
        AIR_ALERT_LASTED.format(
            duration=format_span(lowered_at - raised_at),
            start=f"{calendar.local_time(raised_at):%H:%M}",
            end=f"{calendar.local_time(lowered_at):%H:%M}",
        )
    )
    return "\n\n".join(lines)
