"""Comparing how long the station holds against the hour the schedule promises the light back."""
from datetime import datetime, timedelta

from src.modules.power.domain import EcoFlowState, GridState, OutageForecast, OutageSchedule
from src.modules.power.mains_monitor import classify_grid_from_station


def forecast_outage(
    state: EcoFlowState | None,
    schedule: OutageSchedule | None,
    moment: datetime,
    grid: GridState,
) -> OutageForecast | None:
    """
    Answer whether the battery reaches the scheduled return of power, or say nothing when it cannot be known.

    the station's own runtime estimate is used rather than a consumption model of our own: it already accounts
    for what the flat is drawing right now, which is the hard half of the question. `moment` is local wall
    clock, because the schedule counts minutes from local midnight.
    """
    if state is None or not state.remaining_minutes:
        return None
    if not _the_flat_is_on_battery(grid, state):
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


def _the_flat_is_on_battery(grid: GridState, state: EcoFlowState) -> bool:
    """
    Whether the light is actually out, measured where it can be measured.

    the hat is wired to the wall socket and the station is not: a station idling with its own output on looks
    exactly like one carrying the flat through a blackout, and on 13 october it said so for nine minutes after
    the light had already come back — which is a warning about an outage that had ended. the hat decides
    wherever it can answer, and the station is consulted only when it cannot.
    """
    if grid is not GridState.UNKNOWN:
        return grid is GridState.ON_BATTERY
    return classify_grid_from_station(state) is GridState.ON_BATTERY
