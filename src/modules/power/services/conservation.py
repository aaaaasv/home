"""
EcoFlow Delta 2 storage-conservation logic — pure decisions over timestamps, no i/o.

The station is "conserved" once it drops off ble (switched off or shelved): we keep the last known charge and the
moment we lost sight of it, then reason purely from elapsed time plus an assumed self-discharge, and — whenever the
station is briefly powered and visible — watch its charge trace for a completed maintenance cycle.

Thresholds come from the Delta 2 manual and LiFePO4 storage guidance (see docs/power-topic-design.md). Ukrainian
never appears here: evaluate() returns a structured advisory (level + kind + numbers) and the bot layer renders it.

Consolidation bands read the charge at the moment of storage. The design fixes four points — ≤5 red, <30 yellow,
50–80 green, >90 blue — and leaves two gaps (30–50, 80–90); both are resolved toward silence, this module's ethos:

    p ≤ 5          RED     charge to ~60 now
    5 < p < 30     YELLOW  top up toward ~60
    30 ≤ p ≤ 90    GREEN   healthy enough — say nothing loud
    p > 90         BLUE    discharge toward ~60
"""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum

from src.common.domain import DomainModel


class ConservationMode(StrEnum):
    # off the grid entirely (shelf storage) vs wired as a UPS/EPS, which self-discharges far faster
    OFF = "off"
    UPS = "ups"


class ConservationLevel(StrEnum):
    # green is card-only (no push); blue is an informational "discharge a bit"; yellow/red are the ones that ping
    GREEN = "green"
    BLUE = "blue"
    YELLOW = "yellow"
    RED = "red"


class ConservationKind(StrEnum):
    CONSOLIDATION = "consolidation"
    CYCLE_DUE = "cycle_due"
    WARRANTY = "warranty"
    ZERO_PROTECTION = "zero_protection"


STORAGE_TARGET_PERCENT = 60
# the storage-moment advice applies only right after we lose sight of the station; after that the ongoing watches
# (drift toward empty, the maintenance cycle, the warranty limit) take over
CONSOLIDATION_WINDOW_DAYS = 2
SELF_DISCHARGE_PERCENT_PER_DAY = {ConservationMode.OFF: 0.8, ConservationMode.UPS: 4.0}
# a full 60→0→100→60 calibration cycle is due this often; UPS drains so fast it wants the cycle far sooner
CYCLE_INTERVAL_DAYS = {ConservationMode.OFF: 90, ConservationMode.UPS: 30}
CYCLE_LEAD_DAYS = 7
# the manufacturer voids the warranty past this many days without a full cycle; start nagging before the wall
WARRANTY_LIMIT_DAYS = 180
WARRANTY_ALERT_DAYS = 170
ZERO_PROTECTION_URGENT_PERCENT = 10.0
ZERO_PROTECTION_WARN_PERCENT = 20.0
CONSOLIDATION_URGENT_PERCENT = 5.0
CONSOLIDATION_LOW_PERCENT = 30.0
CONSOLIDATION_HIGH_PERCENT = 90.0
# a cycle counts as done when the trace dips to the floor and then climbs back to (near) full
CYCLE_DETECT_LOW_PERCENT = 5.0
CYCLE_DETECT_HIGH_PERCENT = 95.0

SECONDS_PER_DAY = 86400


class ConservationState(DomainModel):
    """The last we saw of a conserved station: its charge, when we lost sight of it, its mode, and its last cycle"""

    stored_percent: float
    stored_at: datetime
    mode: ConservationMode
    last_cycle_at: datetime | None = None


class ConservationAdvisory(DomainModel):
    """The single most important thing to say about a conserved station now; the bot layer maps it to Ukrainian"""

    level: ConservationLevel
    kind: ConservationKind
    target_percent: int | None = None
    estimated_percent: int | None = None
    days_since_cycle: int | None = None
    days_until_cycle: int | None = None
    days_until_warranty: int | None = None


def estimate_percent(state: ConservationState, now: datetime) -> float:
    """Current charge estimate from the stored charge minus the mode's self-discharge over the elapsed time"""
    elapsed_days = max(0.0, (now - state.stored_at).total_seconds() / SECONDS_PER_DAY)
    drain = SELF_DISCHARGE_PERCENT_PER_DAY[state.mode] * elapsed_days
    return max(0.0, state.stored_percent - drain)


def days_since_last_cycle(state: ConservationState, now: datetime) -> int:
    # never cycled → count from when we started storing it, which is the best "clean" reference we have
    reference = state.last_cycle_at or state.stored_at
    return (now - reference).days


def detect_completed_cycle(
    readings: Sequence[tuple[datetime, float]],
    after: datetime | None = None,
    low_threshold: float = CYCLE_DETECT_LOW_PERCENT,
    high_threshold: float = CYCLE_DETECT_HIGH_PERCENT,
) -> datetime | None:
    """
    Return when a maintenance cycle completed within `readings`, else None.

    `readings` is an ascending time-ordered sequence of (moment, charge_percent). A cycle counts as complete when
    the charge first dips to `low_threshold` or below and later climbs to `high_threshold` or above; the returned
    moment is that of the first qualifying high reading. `after` (e.g. the last recorded cycle) skips readings up
    to and including it, so an earlier cycle is not re-detected.
    """
    seen_low = False
    for moment, percent in readings:
        if after is not None and moment <= after:
            continue
        if percent <= low_threshold:
            seen_low = True
        elif seen_low and percent >= high_threshold:
            return moment
    return None


def evaluate(state: ConservationState, now: datetime) -> ConservationAdvisory | None:
    """
    The single most important advisory for a conserved station right now, or None when nothing needs saying.

    Silent by default, like the deadline cards: a station stored well and not near a cycle returns None. Ordered by
    consequence — a warranty-voiding gap tops everything; while the user is actively handling the pack (the fresh
    window) the storage-moment advice leads; otherwise imminent cell damage beats an overdue cycle beats a slow
    drift beats the quiet cycle heads-up.
    """
    days_since_cycle = days_since_last_cycle(state, now)
    estimated = estimate_percent(state, now)
    cadence = CYCLE_INTERVAL_DAYS[state.mode]
    is_fresh = (now - state.stored_at).days < CONSOLIDATION_WINDOW_DAYS
    consolidation = _consolidation_advisory(state, estimated) if is_fresh else None

    # 1. warranty hard limit — the costliest outcome, and it repeats every day until a cycle clears it
    if days_since_cycle >= WARRANTY_ALERT_DAYS:
        return ConservationAdvisory(
            level=ConservationLevel.RED,
            kind=ConservationKind.WARRANTY,
            days_since_cycle=days_since_cycle,
            days_until_warranty=max(0, WARRANTY_LIMIT_DAYS - days_since_cycle),
            estimated_percent=round(estimated),
        )
    # 2. within the storage-moment window a low/high charge is the active advice, framed as consolidation
    if consolidation is not None and consolidation.level != ConservationLevel.GREEN:
        return consolidation
    # 3. deep-discharge cell damage imminent
    if estimated <= ZERO_PROTECTION_URGENT_PERCENT:
        return _zero_protection(ConservationLevel.RED, estimated)
    # 4. the calibration cycle is overdue — a scheduled maintenance outranks a merely-low charge, since running it
    #    (discharge to zero, charge to full, settle to 60) resolves both
    if days_since_cycle >= cadence:
        return _cycle_due(ConservationLevel.YELLOW, days_since_cycle, 0)
    # 5. drifting toward empty
    if estimated <= ZERO_PROTECTION_WARN_PERCENT:
        return _zero_protection(ConservationLevel.YELLOW, estimated)
    # 6. the calibration cycle is approaching — a quiet, card-only heads-up
    if days_since_cycle >= cadence - CYCLE_LEAD_DAYS:
        return _cycle_due(ConservationLevel.GREEN, days_since_cycle, cadence - days_since_cycle)
    # 7. freshly stored in the healthy band — a calm acknowledgement
    if consolidation is not None:
        return consolidation
    return None


def _consolidation_advisory(state: ConservationState, estimated: float) -> ConservationAdvisory:
    percent = state.stored_percent
    if percent <= CONSOLIDATION_URGENT_PERCENT:
        level = ConservationLevel.RED
    elif percent < CONSOLIDATION_LOW_PERCENT:
        level = ConservationLevel.YELLOW
    elif percent > CONSOLIDATION_HIGH_PERCENT:
        level = ConservationLevel.BLUE
    else:
        level = ConservationLevel.GREEN
    return ConservationAdvisory(
        level=level,
        kind=ConservationKind.CONSOLIDATION,
        target_percent=STORAGE_TARGET_PERCENT,
        estimated_percent=round(estimated),
    )


def _zero_protection(level: ConservationLevel, estimated: float) -> ConservationAdvisory:
    return ConservationAdvisory(
        level=level,
        kind=ConservationKind.ZERO_PROTECTION,
        target_percent=STORAGE_TARGET_PERCENT,
        estimated_percent=round(estimated),
    )


def _cycle_due(level: ConservationLevel, days_since_cycle: int, days_until_cycle: int) -> ConservationAdvisory:
    return ConservationAdvisory(
        level=level,
        kind=ConservationKind.CYCLE_DUE,
        days_since_cycle=days_since_cycle,
        days_until_cycle=days_until_cycle,
    )
