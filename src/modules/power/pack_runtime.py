"""How long the pi's own pack has left, and when that is worth saying out loud."""
from datetime import timedelta
from itertools import pairwise

from src.modules.power.domain import PackWarning, UpsState

# volts at the hat's gauge → minutes before the host agent halts the pi at 3.40 V. read off the two discharges
# that ran all the way to the cut-off, 10.09 and 14.10.2026, which agreed within five minutes at every step.
#
# **this is a curve and not a rate on purpose.** percent per hour looked like the obvious model and is wrong
# where it matters: the gauge reports 15% with 1 h 22 min left and 0.1% with 33 min left, so a linear
# 17.6%/h — the average over the whole run — promises 51 minutes at the first and nothing at all at the
# second. volts fall unevenly but they fall monotonically, and two independent runs put the same minute
# against the same voltage.
PACK_RUNTIME_CURVE = (
    (4.15, 345),
    (4.10, 338),
    (4.05, 324),
    (4.00, 275),
    (3.95, 244),
    (3.90, 227),
    (3.85, 205),
    (3.80, 179),
    (3.75, 155),
    (3.70, 132),
    (3.65, 109),
    (3.60, 86),
    (3.55, 62),
    (3.50, 38),
    (3.45, 20),
    (3.42, 10),
    (3.40, 0),
)


def estimate_pack_runtime(battery_volts: float) -> timedelta:
    """
    Minutes left at this voltage, interpolated between the measured steps.

    a pack resting above the top of the curve has just finished charging and gets the full run; one below
    the bottom is already at the halt the agent takes at that voltage, which is zero rather than negative.
    """
    if battery_volts >= PACK_RUNTIME_CURVE[0][0]:
        return timedelta(minutes=PACK_RUNTIME_CURVE[0][1])

    for (upper_volts, upper_minutes), (lower_volts, lower_minutes) in pairwise(PACK_RUNTIME_CURVE):
        if battery_volts >= lower_volts:
            share = (battery_volts - lower_volts) / (upper_volts - lower_volts)
            return timedelta(minutes=round(lower_minutes + share * (upper_minutes - lower_minutes)))
    return timedelta(0)


def classify_pack(ups: UpsState | None, warning_at: timedelta, goodbye_at: timedelta) -> PackWarning | None:
    """
    Whether the pack has reached one of the two moments worth a push, counted in time rather than in charge.

    a live socket is the end of the matter whatever the pack reads — it is charging, and the family asked to
    hear about running out, not about being half full. a hat that cannot be read says nothing at all: a
    missing reading is not an empty pack, and this message wakes the house.
    """
    if ups is None or ups.mains_present:
        return None

    remaining = estimate_pack_runtime(ups.battery_volts)
    if remaining <= goodbye_at:
        return PackWarning.HALTING
    if remaining <= warning_at:
        return PackWarning.LOW
    return None
