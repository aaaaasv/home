"""Four layers, four different kinds of sensor, one board — this is where they are reduced to the same row."""
from datetime import datetime, timedelta

from src.modules.power.domain import (
    EcoFlowState,
    GridState,
    Reserve,
    ReserveLayer,
    ReserveRow,
    ReserveStanding,
    UpsState,
)

# a 1S 18650 resting above this has finished charging. the gauge's own percent decides nothing here: it re-learns
# the pack after a cell swap and reads nonsense meanwhile — 4% at 3.78 V on 08.09, which was really about 45%
PACK_FULL_VOLTS = 4.15


def build_reserve(
    grid: GridState,
    station: EcoFlowState | None,
    ups: UpsState | None,
    router_alive: bool,
    on_battery_for: timedelta | None,
    socket_dead_for: timedelta | None,
) -> Reserve:
    """
    Assemble the board from whatever each layer can currently say, without letting any of them speak for another.

    two clocks run through here and they are not the same one. `on_battery_for` is the city's — it is what the
    heading answers, and it keeps counting after the transfer switch is thrown. `socket_dead_for` is the flat's
    wall socket, which is what the pi and the router actually run from: throw the switch mid-outage and the
    socket comes back to life on the station, so those two rows stop holding and start charging while the city
    is still out. collapsing them into one number would make the board lie in exactly the hour it matters.
    """
    socket_live = ups.mains_present if ups is not None else None
    return Reserve(
        grid=grid,
        rows=(
            _station_row(station),
            _pi_row(ups, socket_dead_for),
            _router_row(router_alive, socket_live, socket_dead_for),
        ),
        on_battery_for=on_battery_for if grid is GridState.ON_BATTERY else None,
    )


def _station_row(station: EcoFlowState | None) -> ReserveRow:
    """
    The one layer that measures its own runtime, so its row is read straight off the station's own watts.

    `on_mains` is deliberately unused: it tracks whether the station is drawing, and a full station idling on
    mains reports it false. the watts say the same thing without the ambiguity.
    """
    if station is None:
        return ReserveRow(layer=ReserveLayer.STATION, standing=ReserveStanding.UNREACHABLE)

    remaining = timedelta(minutes=station.remaining_minutes) if station.remaining_minutes else None
    if station.ac_input_power:
        return ReserveRow(layer=ReserveLayer.STATION, standing=ReserveStanding.CHARGING, remaining=remaining)
    if station.ac_output_power:
        return ReserveRow(layer=ReserveLayer.STATION, standing=ReserveStanding.HOLDING, remaining=remaining)
    return ReserveRow(layer=ReserveLayer.STATION, standing=ReserveStanding.FULL)


def _pi_row(ups: UpsState | None, socket_dead_for: timedelta | None) -> ReserveRow:
    """The hat knows whether its socket is live and how full its pack is, but nothing about how long it lasts."""
    if ups is None:
        return ReserveRow(layer=ReserveLayer.PI, standing=ReserveStanding.UNREACHABLE)
    if not ups.mains_present:
        return ReserveRow(
            layer=ReserveLayer.PI, standing=ReserveStanding.HOLDING_UNMEASURED, holding_for=socket_dead_for
        )
    if ups.battery_volts >= PACK_FULL_VOLTS:
        return ReserveRow(layer=ReserveLayer.PI, standing=ReserveStanding.FULL)
    return ReserveRow(layer=ReserveLayer.PI, standing=ReserveStanding.CHARGING)


def _router_row(router_alive: bool, socket_live: bool | None, socket_dead_for: timedelta | None) -> ReserveRow:
    """
    The 2E has no data interface at all, so this row is a reachability probe plus what the hat says about the socket.

    with no hat to ask, the row stops at "alive": claiming it runs on battery would be inventing the one number
    this layer is least able to give.
    """
    if not router_alive:
        return ReserveRow(layer=ReserveLayer.ROUTER, standing=ReserveStanding.UNREACHABLE)
    if socket_live is False:
        return ReserveRow(
            layer=ReserveLayer.ROUTER, standing=ReserveStanding.HOLDING_UNMEASURED, holding_for=socket_dead_for
        )
    return ReserveRow(layer=ReserveLayer.ROUTER, standing=ReserveStanding.ALIVE)


class ElapsedClock:
    """
    How long something has been true — but only counted from a start that was actually watched.

    a bot that comes up in the middle of an outage would otherwise report it as one minute old, which is the
    same mistake `MainsMonitor` refuses to make when it declines to announce the outage it woke up inside.
    until a reading has seen the condition false at least once, there is no honest number and it says so.
    """

    def __init__(self) -> None:
        self._since: datetime | None = None
        self._watched_it_start = False

    def update(self, holds: bool, now: datetime) -> timedelta | None:
        if not holds:
            self._since = None
            self._watched_it_start = True
            return None
        if not self._watched_it_start:
            return None
        if self._since is None:
            self._since = now
        return now - self._since
