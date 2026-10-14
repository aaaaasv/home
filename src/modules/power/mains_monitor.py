"""Deciding whether the city grid is up, and noticing the moment it changes."""
from src.modules.power.domain import DeclaredSupply, EcoFlowState, GridState, UpsState


def classify_grid(ups: UpsState | None, declared_supply: DeclaredSupply = DeclaredSupply.GRID) -> GridState:
    """
    Answer from the pi's own hat, which is wired to the wall socket, and refuse to answer without it.

    the station used to get a vote here, from the days before the hat existed. it never could have one: its
    firmware exposes watts and no "plugged in" flag, so a station sitting unplugged and running a load is
    indistinguishable from one carrying the flat through a blackout. that ambiguity was known and written
    down before the hat was fitted, and keeping the inference afterwards cost real announcements in both
    directions — a blackout reported as calm, and the light coming back never reported at all.

    the hat is a measurement, and the one thing it cannot measure is which wire its socket is on. while the
    family says the station is feeding that socket, mains voltage there is the station's own output and says
    nothing about the city — so it reads as battery, which is what the flat is actually running on.
    """
    if ups is None:
        return GridState.UNKNOWN
    if not ups.mains_present:
        return GridState.ON_BATTERY
    return GridState.ON_BATTERY if declared_supply is DeclaredSupply.STATION else GridState.ON_GRID


def classify_grid_from_station(state: EcoFlowState | None) -> GridState:
    """
    What the station alone says about its own supply — for the station's own card, never for the grid.

    the delta 2 has no "plugged in" flag, so this is an inference: drawing from the wall means its input is
    live, drawing nothing while feeding a load means it is on battery. but a full station idling on mains
    also draws nothing, and that looks identical — hence the third answer.
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

    a reading the hat cannot give is skipped rather than treated as a change, so a stopped agent never
    announces a blackout. a change must be seen twice before it is announced, because one reading is a blip
    and this message wakes the family.

    where the grid stood last is read back from the recorded events through `seed`, because the process
    restarts on every deploy and in-memory state alone made the first change after a restart indistinguishable
    from the reading that merely established a baseline. it was swallowed, every time: the hat logged nine
    outages over three days and the family heard about none of them.
    """

    def __init__(self, confirmations: int = 2):
        self.confirmations = confirmations
        self._announced: GridState | None = None
        self._pending: GridState | None = None
        self._seen = 0

    def seed(self, announced: GridState | None) -> None:
        """Where the grid stood when this house last said something about it, so a restart repeats nothing."""
        self._announced = announced

    def update(self, ups: UpsState | None, declared_supply: DeclaredSupply = DeclaredSupply.GRID) -> GridState | None:
        """Return the new grid state at the moment it is confirmed, and None every other time."""
        grid = classify_grid(ups, declared_supply)
        if grid is GridState.UNKNOWN:
            return None

        if grid != self._pending:
            self._pending = grid
            self._seen = 1
        else:
            self._seen += 1

        if self._seen < self.confirmations or grid == self._announced:
            return None

        # "світло є" is worth nothing on its own, so a house that has never said anything stays quiet about it;
        # "світло зникло" is the message this whole layer exists for and is said even as the very first word
        if self._announced is None and grid is GridState.ON_GRID:
            self._announced = grid
            return None

        self._announced = grid
        return grid
