"""
How hot the server shelf is allowed to get, and when that is worth a message.

The wired SHT31 hangs off the Pi by a short I²C ribbon, so it has measured the shelf — not a room — since the
Pi moved there. That makes it the one sensor standing where the heat actually is: a Pi, a router, an eight-year
-old laptop and, soon, two 18650 cells charging at a few amps. Read that way it stops being a decorative number
and becomes an early warning.
"""
from dataclasses import dataclass

from src.modules.room_climate.domain import RoomClimate

# the laptop and the cells are unhappy above this, and it is the first number worth saying out loud
SHELF_WARM_CELSIUS = 40.0
# charging lithium above this shortens its life measurably, so it is called out as its own, worse case
SHELF_HOT_CELSIUS = 45.0
# a shelf that drifts around a threshold must not cost a message an hour, so recovery sits well below it
SHELF_RECOVERED_CELSIUS = 37.0

WARM = "warm"
HOT = "hot"


@dataclass(frozen=True)
class ShelfHeatVerdict:
    """What to say now, given what the shelf reads and what has already been said."""

    level: str | None
    recovered: bool


class ShelfHeatMonitor:
    """
    Turns a shelf temperature plus the card already standing into one of three answers: say this, clear, or nothing.

    the card is the state, exactly as the battery monitor does it — a shelf sitting at forty-one must be reported
    once, not every time the job runs, and the report must escalate on its own if it climbs past forty-five.
    """

    def evaluate(self, climate: RoomClimate | None, carded_level: str | None) -> ShelfHeatVerdict:
        if climate is None:
            return ShelfHeatVerdict(level=None, recovered=False)

        temperature = climate.temperature_celsius
        if temperature >= SHELF_HOT_CELSIUS:
            return ShelfHeatVerdict(level=None if carded_level == HOT else HOT, recovered=False)
        if temperature >= SHELF_WARM_CELSIUS:
            # a shelf cooling from hot to warm is not news; only the way up earns a second message
            return ShelfHeatVerdict(level=None if carded_level is not None else WARM, recovered=False)
        if carded_level is not None and temperature < SHELF_RECOVERED_CELSIUS:
            return ShelfHeatVerdict(level=None, recovered=True)
        return ShelfHeatVerdict(level=None, recovered=False)
