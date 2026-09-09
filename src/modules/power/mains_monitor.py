"""Deciding whether the city grid is up, and noticing the moment it changes."""
from src.modules.power.domain import EcoFlowState, GridState, UpsState


def classify_grid(ups: UpsState | None, station: EcoFlowState | None) -> GridState:
    """
    Answer from the pi's own hat where it can, from the station's watts where it cannot, and refuse otherwise.

    the hat's line is wired to the socket, so it is a measurement rather than an inference — but after the
    transfer switch is thrown the whole flat, this pi included, runs off the station, and the line then reports
    the station's power as if it were the city's. the station feeding the flat is what tells those two apart.
    """
    if ups is not None:
        if not ups.mains_present:
            return GridState.ON_BATTERY
        # only a discharging station is evidence of the switch: one drawing from the wall while it feeds the
        # flat is proof of the opposite, and an idle or unreachable one is no evidence either way
        if classify_grid_from_station(station) is GridState.ON_BATTERY:
            return GridState.ON_BATTERY
        return GridState.ON_GRID

    return classify_grid_from_station(station)


def classify_grid_from_station(state: EcoFlowState | None) -> GridState:
    """
    Read the grid off the station alone, and refuse to answer when the reading cannot carry the question.

    the delta 2 has no "plugged in" flag — its firmware exposes only watts, and the newer stations' explicit
    flag does not exist here — so mains presence has to be inferred. drawing from the wall is proof the grid
    is up. drawing nothing while feeding the flat is proof it is down. but a full station idling on mains
    also draws nothing, and that looks identical to an outage: hence the third answer.
    """
    if state is None:
        return GridState.UNKNOWN
    if state.ac_input_power > 0:
        return GridState.ON_GRID
    if state.ac_output_power > 0:
        return GridState.ON_BATTERY
    return GridState.UNKNOWN


class MainsMonitor:
    """
    Reports the moment the grid goes and the moment it comes back, and says nothing in between.

    unknown readings are skipped rather than treated as a change, so a station that is unreachable, shelved or
    simply idle never announces a blackout. a change must be seen twice before it is announced, because one
    reading is a blip and this message wakes the family. state is in memory and re-seeds from the first known
    reading after a restart, so a deploy cannot fire a spurious "світло зникло".
    """

    def __init__(self, confirmations: int = 2):
        self.confirmations = confirmations
        self._announced: GridState | None = None
        self._pending: GridState | None = None
        self._seen = 0

    def update(self, ups: UpsState | None, station: EcoFlowState | None) -> GridState | None:
        """Return the new grid state at the moment it is confirmed, and None every other time."""
        grid = classify_grid(ups, station)
        if grid is GridState.UNKNOWN:
            return None

        if grid != self._pending:
            self._pending = grid
            self._seen = 1
        else:
            self._seen += 1

        if self._seen < self.confirmations or grid == self._announced:
            return None

        first_reading = self._announced is None
        self._announced = grid
        # the first known reading only establishes where we started; announcing it would greet every deploy
        # with a blackout report
        return None if first_reading else grid
