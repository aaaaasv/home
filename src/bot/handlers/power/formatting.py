"""How the EcoFlow card, the outage schedule and the conservation card render."""
from datetime import datetime

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
    POWER_MAINS_LOST_NO_ESTIMATE,
    POWER_MAINS_RESTORED,
    POWER_OUTAGE_SHORTFALL,
    POWER_SCHEDULE_AS_OF,
    POWER_SCHEDULE_EMERGENCY_NOTE,
    POWER_SCHEDULE_INTERVAL,
    POWER_SCHEDULE_TITLE,
)
from src.modules.power.domain import EcoFlowState, GridState, OutageForecast, OutageSchedule, OutageScheduleStatus
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


def render_mains_change(grid: GridState, state: EcoFlowState) -> str:
    """What the family reads when the lights go out, and when they come back."""
    battery = round(state.battery_percent)
    if grid is GridState.ON_GRID:
        return POWER_MAINS_RESTORED.format(battery=battery)
    if state.remaining_minutes is None:
        return POWER_MAINS_LOST_NO_ESTIMATE.format(battery=battery)
    return POWER_MAINS_LOST.format(battery=battery, duration=_format_runtime(state.remaining_minutes))


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
