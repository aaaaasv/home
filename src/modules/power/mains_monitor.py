"""Deciding, from what the station reports, whether the grid is up — and noticing the moment it changes."""
from src.modules.power.domain import EcoFlowState, GridState


def classify_grid(state: EcoFlowState | None) -> GridState:
    """
    Read the grid off the station, and refuse to answer when the reading cannot carry the question.

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

    def update(self, state: EcoFlowState | None) -> GridState | None:
        """Return the new grid state at the moment it is confirmed, and None every other time."""
        grid = classify_grid(state)
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
