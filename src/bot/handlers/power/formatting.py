"""How the EcoFlow card, the reserve board, the outage schedule and the conservation card render."""
from datetime import datetime, timedelta

from src.bot.handlers.power.messages import (
    POWER_CONSERVATION_CYCLE_DUE,
    POWER_CONSERVATION_CYCLE_SOON,
    POWER_CONSERVATION_IN_USE,
    POWER_CONSERVATION_IN_USE_PERCENT,
    POWER_CONSERVATION_STORE_BLUE,
    POWER_CONSERVATION_STORE_GREEN,
    POWER_CONSERVATION_STORE_RED,
    POWER_CONSERVATION_STORE_YELLOW,
    POWER_CONSERVATION_STORED,
    POWER_CONSERVATION_WARRANTY,
    POWER_ECOFLOW_AS_OF,
    POWER_ECOFLOW_ON_BATTERY,
    POWER_ECOFLOW_ON_MAINS,
    POWER_ECOFLOW_ON_MAINS_CHARGING,
    POWER_ECOFLOW_OUTPUT,
    POWER_ECOFLOW_TIME_LEFT,
    POWER_ECOFLOW_TIME_TO_FULL,
    POWER_ECOFLOW_TITLE,
    POWER_MAINS_LOST,
    POWER_MAINS_RESTORED,
    POWER_OUTAGE_SHORTFALL,
    POWER_RESERVE_ALIVE,
    POWER_RESERVE_AS_OF,
    POWER_RESERVE_CHARGING,
    POWER_RESERVE_CHARGING_UNTIMED,
    POWER_RESERVE_FULL,
    POWER_RESERVE_HOLDING,
    POWER_RESERVE_HOLDING_UNMEASURED,
    POWER_RESERVE_HOLDING_UNMEASURED_UNTIMED,
    POWER_RESERVE_LAYER_MEDIA_SERVER,
    POWER_RESERVE_LAYER_PI,
    POWER_RESERVE_LAYER_ROUTER,
    POWER_RESERVE_LAYER_STATION,
    POWER_RESERVE_ROW,
    POWER_RESERVE_ROW_WITH_CHARGE,
    POWER_RESERVE_TITLE_ON_BATTERY,
    POWER_RESERVE_TITLE_ON_BATTERY_UNTIMED,
    POWER_RESERVE_TITLE_ON_GRID,
    POWER_RESERVE_TITLE_UNKNOWN,
    POWER_RESERVE_UNREACHABLE,
    POWER_SCHEDULE_AS_OF,
    POWER_SCHEDULE_EMERGENCY_NOTE,
    POWER_SCHEDULE_INTERVAL,
    POWER_SCHEDULE_TITLE,
)
from src.modules.power.domain import (
    EcoFlowState,
    GridState,
    OutageForecast,
    OutageSchedule,
    OutageScheduleStatus,
    Reserve,
    ReserveLayer,
    ReserveRow,
    ReserveStanding,
)
from src.modules.power.services.conservation import ConservationAdvisory, ConservationKind, ConservationLevel


def render_ecoflow(state: EcoFlowState) -> str:
    lines = [f"{POWER_ECOFLOW_TITLE} — {round(state.battery_percent)}%"]

    if state.on_mains:
        source = (
            POWER_ECOFLOW_ON_MAINS_CHARGING.format(watts=state.ac_input_power)
            if state.ac_input_power
            else POWER_ECOFLOW_ON_MAINS
        )
        if state.remaining_minutes:
            source += " · " + POWER_ECOFLOW_TIME_TO_FULL.format(duration=_format_runtime(state.remaining_minutes))
    else:
        source = POWER_ECOFLOW_ON_BATTERY
        if state.remaining_minutes:
            source += " · " + POWER_ECOFLOW_TIME_LEFT.format(duration=_format_runtime(state.remaining_minutes))
    lines.append(source)

    if state.ac_output_power:
        lines.append(POWER_ECOFLOW_OUTPUT.format(watts=state.ac_output_power))

    lines.extend(["", POWER_ECOFLOW_AS_OF.format(time=f"{state.as_of:%H:%M}")])
    return "\n".join(lines)


def _format_runtime(minutes: int) -> str:
    hours, remaining_minutes = divmod(minutes, 60)
    if hours and remaining_minutes:
        return f"{hours} год {remaining_minutes} хв"
    if hours:
        return f"{hours} год"
    return f"{remaining_minutes} хв"


def render_mains_change(grid: GridState) -> str:
    """
    What the family reads when the lights go out, and when they come back — the fact, and nothing beside it.

    it used to carry the station's charge and runtime too, and that was the wrong place for them: this push
    fires at three in the morning, and what it has to deliver in one glance is a single word. the numbers are
    on the reserve board, which is refreshed every minute through an outage and is one tap away.
    """
    return POWER_MAINS_RESTORED if grid is GridState.ON_GRID else POWER_MAINS_LOST


RESERVE_LAYER_LABELS = {
    ReserveLayer.STATION: POWER_RESERVE_LAYER_STATION,
    ReserveLayer.PI: POWER_RESERVE_LAYER_PI,
    ReserveLayer.ROUTER: POWER_RESERVE_LAYER_ROUTER,
    ReserveLayer.MEDIA_SERVER: POWER_RESERVE_LAYER_MEDIA_SERVER,
}


def render_reserve_board(reserve: Reserve, generated_at: datetime) -> str:
    """
    The whole reserve on one screen: one heading for the grid, then one line per layer, all in the same unit.

    the heading carries the grid because it is one fact about the flat rather than four about the devices —
    which is what lets every row below it be about time and nothing else.
    """
    lines = [_render_reserve_title(reserve), ""]
    lines.extend(_render_reserve_row(row) for row in reserve.rows)
    lines.extend(["", POWER_RESERVE_AS_OF.format(time=f"{generated_at:%H:%M}")])
    return "\n".join(lines)


def _render_reserve_title(reserve: Reserve) -> str:
    if reserve.grid is GridState.ON_GRID:
        return POWER_RESERVE_TITLE_ON_GRID
    if reserve.grid is GridState.UNKNOWN:
        return POWER_RESERVE_TITLE_UNKNOWN
    if reserve.on_battery_for is None:
        return POWER_RESERVE_TITLE_ON_BATTERY_UNTIMED
    return POWER_RESERVE_TITLE_ON_BATTERY.format(duration=_format_duration(reserve.on_battery_for))


def _render_reserve_row(row: ReserveRow) -> str:
    layer = RESERVE_LAYER_LABELS[row.layer]
    standing = _render_reserve_standing(row)
    if row.charge_percent is None:
        return POWER_RESERVE_ROW.format(layer=layer, standing=standing)
    return POWER_RESERVE_ROW_WITH_CHARGE.format(layer=layer, charge=row.charge_percent, standing=standing)


def _render_reserve_standing(row: ReserveRow) -> str:
    if row.standing is ReserveStanding.HOLDING and row.remaining is not None:
        return POWER_RESERVE_HOLDING.format(duration=_format_duration(row.remaining))
    if row.standing is ReserveStanding.CHARGING and row.remaining is not None:
        return POWER_RESERVE_CHARGING.format(duration=_format_duration(row.remaining))
    if row.standing is ReserveStanding.HOLDING_UNMEASURED and row.holding_for is not None:
        return POWER_RESERVE_HOLDING_UNMEASURED.format(duration=_format_duration(row.holding_for))
    # a layer that cannot say how long falls back to the bare state, which is still worth a line
    return {
        ReserveStanding.HOLDING: POWER_RESERVE_HOLDING_UNMEASURED_UNTIMED,
        ReserveStanding.HOLDING_UNMEASURED: POWER_RESERVE_HOLDING_UNMEASURED_UNTIMED,
        ReserveStanding.CHARGING: POWER_RESERVE_CHARGING_UNTIMED,
        ReserveStanding.FULL: POWER_RESERVE_FULL,
        ReserveStanding.ALIVE: POWER_RESERVE_ALIVE,
        ReserveStanding.UNREACHABLE: POWER_RESERVE_UNREACHABLE,
    }[row.standing]


def _format_duration(duration: timedelta) -> str:
    return _format_runtime(round(duration.total_seconds() / 60))


def render_outage_forecast(forecast: OutageForecast) -> str:
    """The one sentence this feature exists for: the deadline, and the gap the family has to close."""
    return POWER_OUTAGE_SHORTFALL.format(
        runs_out=forecast.runs_out_at.strftime("%H:%M"),
        returns=forecast.power_returns_at.strftime("%H:%M"),
        shortfall=_format_runtime(round(forecast.shortfall.total_seconds() / 60)),
    )


def render_outage_schedule(schedule: OutageSchedule, generated_at: datetime) -> str:
    lines = [POWER_SCHEDULE_TITLE]
    if schedule.status == OutageScheduleStatus.EMERGENCY_SHUTDOWNS:
        lines.append(POWER_SCHEDULE_EMERGENCY_NOTE)
    for interval in schedule.off_intervals:
        lines.append(POWER_SCHEDULE_INTERVAL.format(start=f"{interval.start:%H:%M}", end=f"{interval.end:%H:%M}"))
    lines.extend(["", POWER_SCHEDULE_AS_OF.format(time=f"{generated_at:%H:%M}")])
    return "\n".join(lines)


def render_conservation_card(advisory: ConservationAdvisory) -> str:
    if advisory.kind == ConservationKind.WARRANTY:
        return POWER_CONSERVATION_WARRANTY.format(days=advisory.days_until_warranty)
    if advisory.kind == ConservationKind.CYCLE_DUE:
        if advisory.level == ConservationLevel.YELLOW:
            return POWER_CONSERVATION_CYCLE_DUE
        return POWER_CONSERVATION_CYCLE_SOON.format(days=advisory.days_until_cycle)

    # consolidation and zero-protection both state the same fact — the charge against the storage target — and the
    # level's colour carries the urgency, so they share one set of templates
    store_templates = {
        ConservationLevel.RED: POWER_CONSERVATION_STORE_RED,
        ConservationLevel.YELLOW: POWER_CONSERVATION_STORE_YELLOW,
        ConservationLevel.BLUE: POWER_CONSERVATION_STORE_BLUE,
        ConservationLevel.GREEN: POWER_CONSERVATION_STORE_GREEN,
    }
    return store_templates[advisory.level].format(estimated=advisory.estimated_percent, target=advisory.target_percent)


def render_conservation_status(is_conserved: bool, percent: int | None, advisory: ConservationAdvisory | None) -> str:
    if not is_conserved:
        return (
            POWER_CONSERVATION_IN_USE if percent is None else POWER_CONSERVATION_IN_USE_PERCENT.format(percent=percent)
        )
    # the advisory card already names the station and its charge, so it stands alone — no second "на зберіганні" line
    if advisory is not None:
        return render_conservation_card(advisory)
    return POWER_CONSERVATION_STORED.format(percent=percent)
