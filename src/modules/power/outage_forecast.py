"""Comparing how long the station holds against the hour the schedule promises the light back."""
from datetime import datetime, timedelta

from src.modules.power.domain import EcoFlowState, GridState, OutageForecast, OutageSchedule
from src.modules.power.mains_monitor import classify_grid


def forecast_outage(
    state: EcoFlowState | None,
    schedule: OutageSchedule | None,
    moment: datetime,
) -> OutageForecast | None:
    """
    Answer whether the battery reaches the scheduled return of power, or say nothing when it cannot be known.

    the station's own runtime estimate is used rather than a consumption model of our own: it already accounts
    for what the flat is drawing right now, which is the hard half of the question. `moment` is local wall
    clock, because the schedule counts minutes from local midnight.
    """
    if state is None or classify_grid(state) is not GridState.ON_BATTERY:
        return None
    if not state.remaining_minutes:
        return None
    if schedule is None or schedule.day != moment.date():
        return None

    interval = schedule.current_off_interval(moment)
    if interval is None:
        # the light is out but the schedule does not say so — an emergency shutdown has no promised end,
        # and inventing one would be worse than staying quiet
        return None

    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return OutageForecast(
        runs_out_at=moment + timedelta(minutes=state.remaining_minutes),
        power_returns_at=midnight + timedelta(minutes=interval.end_minute),
    )
