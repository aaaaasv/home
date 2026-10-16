"""How the EcoFlow card, the reserve board, the outage schedule and the conservation card render."""
from datetime import date, datetime, timedelta

from src.bot.formatting import GENITIVE_MONTH_NAMES, format_duration, format_runtime, format_span
from src.bot.handlers.power.messages import (
    POWER_BOARD_AS_OF,
    POWER_BOARD_ON_THE_STATION,
    POWER_CONSERVATION_CYCLE_DUE,
    POWER_CONSERVATION_CYCLE_SOON,
    POWER_CONSERVATION_IN_USE,
    POWER_CONSERVATION_IN_USE_PERCENT,
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
    POWER_MAINS_LOST_AFTER,
    POWER_MAINS_RESTORED,
    POWER_MAINS_RESTORED_AFTER,
    POWER_OUTAGE_SHORTFALL,
    POWER_OUTAGE_SHORTFALL_OVER,
    POWER_PACK_HALTING,
    POWER_PACK_LOW,
    POWER_RESERVE_ALIVE,
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
    POWER_SCHEDULE_DAY_DATE,
    POWER_SCHEDULE_DAY_TODAY,
    POWER_SCHEDULE_DAY_TOMORROW,
    POWER_SCHEDULE_EMERGENCY_NOTE,
    POWER_SCHEDULE_INTERVAL,
    POWER_SCHEDULE_INTERVAL_NOW,
    POWER_SCHEDULE_NOTHING_LEFT_TODAY,
    POWER_SCHEDULE_NOTHING_TODAY,
    POWER_SCHEDULE_NOTHING_TOMORROW,
    POWER_SCHEDULE_TITLE,
    POWER_SCHEDULE_TOMORROW_UNPUBLISHED,
    POWER_SCHEDULE_UNKNOWN,
)
from src.modules.power.domain import (
    DeclaredSupply,
    EcoFlowState,
    GridState,
    OutageForecast,
    OutageInterval,
    OutageOutlook,
    OutageSchedule,
    OutageScheduleStatus,
    PackWarning,
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
            source += " · " + POWER_ECOFLOW_TIME_TO_FULL.format(duration=format_runtime(state.remaining_minutes))
    else:
        source = POWER_ECOFLOW_ON_BATTERY
        if state.remaining_minutes:
            source += " · " + POWER_ECOFLOW_TIME_LEFT.format(duration=format_runtime(state.remaining_minutes))
    lines.append(source)

    if state.ac_output_power:
        lines.append(POWER_ECOFLOW_OUTPUT.format(watts=state.ac_output_power))

    lines.extend(["", POWER_ECOFLOW_AS_OF.format(time=f"{state.as_of:%H:%M}")])
    return "\n".join(lines)


def render_mains_change(grid: GridState, lasted: timedelta | None = None) -> str:
    """
    What the family reads when the lights go out, and when they come back — the fact, and how long it has been.

    it used to carry the station's charge and runtime too, and that was the wrong place for them: this push
    fires at three in the morning, and what it has to deliver in one glance is a single word. the numbers are
    on the reserve board, which is refreshed every minute through an outage and is one tap away.

    the span is the exception, because it is the one thing nobody can look up afterwards — by the time anybody
    opens a board the outage is over and the clock has moved on.
    """
    if lasted is None:
        return POWER_MAINS_RESTORED if grid is GridState.ON_GRID else POWER_MAINS_LOST
    duration = format_span(lasted)
    if grid is GridState.ON_GRID:
        return POWER_MAINS_RESTORED_AFTER.format(duration=duration)
    return POWER_MAINS_LOST_AFTER.format(duration=duration)


RESERVE_LAYER_LABELS = {
    ReserveLayer.STATION: POWER_RESERVE_LAYER_STATION,
    ReserveLayer.PI: POWER_RESERVE_LAYER_PI,
    ReserveLayer.ROUTER: POWER_RESERVE_LAYER_ROUTER,
    ReserveLayer.MEDIA_SERVER: POWER_RESERVE_LAYER_MEDIA_SERVER,
}


def render_power_board(
    reserve: Reserve | None,
    outlook: OutageOutlook | None,
    generated_at: datetime,
    schedule_expected: bool = False,
) -> str:
    """
    The two questions this topic is opened with, on one card: what we run on, and when the light comes back.

    they were two self-editing boards standing one above the other, which meant two «станом на», two cards
    to find and a reposting rule each. the reserve goes on top because its heading is the one fact about the
    flat — and because it is the half that moves minute by minute, so it is the half worth reading first.

    either half may be missing: a flat with no hat has no reserve to draw, and a clear day has no hours to
    publish. with both gone there is no card at all, which is the caller's cue to clear it away.
    """
    sections = []
    if reserve is not None:
        sections.append(_render_reserve_section(reserve))
    schedule = _render_schedule_section(outlook, generated_at, schedule_expected)
    if schedule:
        sections.append(schedule)
    if not sections:
        return ""

    sections.append([POWER_BOARD_AS_OF.format(time=f"{generated_at:%H:%M}")])
    return "\n\n".join("\n".join(section) for section in sections)


def _render_reserve_section(reserve: Reserve) -> list[str]:
    """
    The whole reserve: one heading for the grid, then one line per layer, all in the same unit.

    the heading carries the grid because it is one fact about the flat rather than four about the devices —
    which is what lets every row below it be about time and nothing else.

    while the family has said the pi hangs on the station, a line says so under the heading: the heading
    is then their word rather than a reading, and a card that reads as certain while it is guessing is
    worse than one that admits it.
    """
    lines = [_render_reserve_title(reserve)]
    if reserve.declared_supply is DeclaredSupply.STATION:
        lines.append(POWER_BOARD_ON_THE_STATION)
    lines.append("")
    lines.extend(_render_reserve_row(row) for row in reserve.rows)
    return lines


def _render_reserve_title(reserve: Reserve) -> str:
    if reserve.grid is GridState.ON_GRID:
        return POWER_RESERVE_TITLE_ON_GRID
    if reserve.grid is GridState.UNKNOWN:
        return POWER_RESERVE_TITLE_UNKNOWN
    if reserve.on_battery_for is None:
        return POWER_RESERVE_TITLE_ON_BATTERY_UNTIMED
    return POWER_RESERVE_TITLE_ON_BATTERY.format(duration=format_duration(reserve.on_battery_for))


def _render_reserve_row(row: ReserveRow) -> str:
    layer = RESERVE_LAYER_LABELS[row.layer]
    standing = _render_reserve_standing(row)
    if row.charge_percent is None:
        return POWER_RESERVE_ROW.format(layer=layer, standing=standing)
    return POWER_RESERVE_ROW_WITH_CHARGE.format(layer=layer, charge=row.charge_percent, standing=standing)


def _render_reserve_standing(row: ReserveRow) -> str:
    if row.standing is ReserveStanding.HOLDING and row.remaining is not None:
        return POWER_RESERVE_HOLDING.format(duration=format_duration(row.remaining))
    if row.standing is ReserveStanding.CHARGING and row.remaining is not None:
        return POWER_RESERVE_CHARGING.format(duration=format_duration(row.remaining))
    if row.standing is ReserveStanding.HOLDING_UNMEASURED and row.holding_for is not None:
        return POWER_RESERVE_HOLDING_UNMEASURED.format(duration=format_duration(row.holding_for))
    # a layer that cannot say how long falls back to the bare state, which is still worth a line
    return {
        ReserveStanding.HOLDING: POWER_RESERVE_HOLDING_UNMEASURED_UNTIMED,
        ReserveStanding.HOLDING_UNMEASURED: POWER_RESERVE_HOLDING_UNMEASURED_UNTIMED,
        ReserveStanding.CHARGING: POWER_RESERVE_CHARGING_UNTIMED,
        ReserveStanding.FULL: POWER_RESERVE_FULL,
        ReserveStanding.ALIVE: POWER_RESERVE_ALIVE,
        ReserveStanding.UNREACHABLE: POWER_RESERVE_UNREACHABLE,
    }[row.standing]


def render_pack_warning(warning: PackWarning, remaining: timedelta) -> str:
    """
    The pi's low pack, in the only unit anyone can act on — and the halting message carries no number at all.

    ten minutes rounded off a measured curve is precision nobody can use, and «вимикається» is already the
    whole of it.
    """
    if warning is PackWarning.HALTING:
        return POWER_PACK_HALTING
    return POWER_PACK_LOW.format(duration=format_duration(remaining))


def render_outage_forecast(forecast: OutageForecast) -> str:
    """The one sentence this feature exists for: the deadline, and the gap the family has to close."""
    return POWER_OUTAGE_SHORTFALL.format(
        runs_out=forecast.runs_out_at.strftime("%H:%M"),
        returns=forecast.power_returns_at.strftime("%H:%M"),
        shortfall=format_runtime(round(forecast.shortfall.total_seconds() / 60)),
    )


def render_outage_recovery(forecast: OutageForecast) -> str:
    """Written over the warning once the draw drops, so the message on screen stops contradicting the station."""
    return POWER_OUTAGE_SHORTFALL_OVER.format(returns=forecast.power_returns_at.strftime("%H:%M"))


def _render_schedule_section(outlook: OutageOutlook | None, generated_at: datetime, expected: bool) -> list[str]:
    """
    Both published days, each interval marked for where the clock already is.

    an hour that has already passed must not read like a forecast — on 7 october yasno published the day's
    intervals at 21:10 and the board announced two outages that were over, which is worse than saying nothing

    a day with nothing ahead still gets its heading and one line. it used to get silence, and silence
    reads the same as a fetch that failed: «я думав чи не вийшло отримати, чи вже не буде відключень».
    a flat that follows no schedule at all gets nothing, because there the silence means what it says.
    """
    if outlook is None or not outlook.has_anything_ahead(generated_at):
        return [POWER_SCHEDULE_TITLE, _render_quiet_day(outlook, generated_at)] if expected else []

    lines = [POWER_SCHEDULE_TITLE]
    # the banner belongs to the grid, not to a calendar day: when the schedule stops applying it stops
    # applying for whatever comes next, so it stands above both days rather than under one of them
    if outlook.today.status is OutageScheduleStatus.EMERGENCY_SHUTDOWNS:
        lines.append(POWER_SCHEDULE_EMERGENCY_NOTE)
    for schedule in (outlook.today, outlook.tomorrow):
        section = _render_day_section(schedule, generated_at) if schedule is not None else []
        if section:
            lines.append("")
            lines.extend(section)
    return lines


def _render_quiet_day(outlook: OutageOutlook | None, generated_at: datetime) -> str:
    """
    What a board says on a day it has nothing to warn about — and it says which kind of nothing.

    yesterday's outlook is not an answer about today: yasno publishes a day whenever it likes, so a
    remembered day that is not this one means the schedule has not been read yet, not that it is clear.
    """
    if outlook is None or outlook.today.day != generated_at.date():
        return POWER_SCHEDULE_UNKNOWN

    today = POWER_SCHEDULE_NOTHING_LEFT_TODAY if outlook.today.off_intervals else POWER_SCHEDULE_NOTHING_TODAY
    # tomorrow is here and still reached this branch, so it has no hours of its own
    tomorrow = POWER_SCHEDULE_NOTHING_TOMORROW if outlook.tomorrow is not None else POWER_SCHEDULE_TOMORROW_UNPUBLISHED
    return f"{today} · {tomorrow}"


def _render_day_section(schedule: OutageSchedule, generated_at: datetime) -> list[str]:
    """
    A day's remaining hours, or nothing at all when it has none left.

    an hour that has finished is dropped rather than struck through: the board answers «коли вимкнуть», and a
    spent hour is not an answer to that.
    """
    # only the day the clock is actually in can have an interval behind or around it
    minute_of_day = generated_at.hour * 60 + generated_at.minute if schedule.day == generated_at.date() else None
    ahead = [
        interval
        for interval in schedule.off_intervals
        if minute_of_day is None or not interval.has_ended_by(minute_of_day)
    ]
    if not ahead:
        return []

    lines = [_render_day_heading(schedule.day, generated_at.date())]
    lines.extend(_render_interval(interval, minute_of_day) for interval in ahead)
    return lines


def _render_day_heading(day: date, today: date) -> str:
    if day == today:
        return POWER_SCHEDULE_DAY_TODAY
    if day == today + timedelta(days=1):
        return POWER_SCHEDULE_DAY_TOMORROW
    return POWER_SCHEDULE_DAY_DATE.format(day=f"{day.day} {GENITIVE_MONTH_NAMES[day.month - 1]}")


def _render_interval(interval: OutageInterval, minute_of_day: int | None) -> str:
    hours = {"start": f"{interval.start:%H:%M}", "end": f"{interval.end:%H:%M}"}
    if minute_of_day is not None and interval.contains_minute(minute_of_day):
        return POWER_SCHEDULE_INTERVAL_NOW.format(**hours)
    return POWER_SCHEDULE_INTERVAL.format(**hours)


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
