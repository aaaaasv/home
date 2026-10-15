"""Reading every backup layer in the flat, which is three local calls and one http one."""
from collections.abc import Callable
from datetime import datetime, tzinfo

from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import GridState, Reserve
from src.modules.power.mains_monitor import classify_grid
from src.modules.power.reserve import ElapsedClock, build_reserve
from src.modules.power.services.ecoflow_station import EcoFlowStation
from src.modules.power.services.media_server_battery import MediaServerBattery
from src.modules.power.services.pi_ups import PiUps
from src.modules.power.services.router_link import RouterLink
from src.modules.power.use_cases.retrieve_declared_supply import RetrieveDeclaredSupplyUseCase


class ReserveReadout:
    """
    What the flat is running on at this moment, with the two clocks that make it a span rather than a state.

    the clocks live here rather than in the job or the card, because they are what the reading knows and the
    job is only its cadence — and because a card reposted after 48h has to keep counting from the same
    moment. they are two and not one on purpose: `build_reserve` explains why the city and the wall socket
    part company.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        ecoflow_station: EcoFlowStation,
        pi_ups: PiUps,
        router_link: RouterLink,
        media_server_battery: MediaServerBattery,
        timezone: tzinfo,
    ):
        self.uow_factory = uow_factory
        self.ecoflow_station = ecoflow_station
        self.pi_ups = pi_ups
        self.router_link = router_link
        self.media_server_battery = media_server_battery
        self.timezone = timezone
        self._on_battery_clock = ElapsedClock()
        self._socket_dead_clock = ElapsedClock()

    async def compose(self) -> Reserve:
        ups = await self.pi_ups.read_state()
        station = await self.ecoflow_station.read_state()
        router_alive = await self.router_link.is_alive()
        media_server = await self.media_server_battery.read_state()
        now = datetime.now(self.timezone)

        # the heading says whether the flat is on the city, and while the pi hangs on the station that is a
        # thing only the family knows — the hat reads mains either way
        declared_supply = await RetrieveDeclaredSupplyUseCase(uow=self.uow_factory())()
        grid = classify_grid(ups, declared_supply)
        return build_reserve(
            grid=grid,
            declared_supply=declared_supply,
            station=station,
            ups=ups,
            router_alive=router_alive,
            media_server=media_server,
            on_battery_for=self._on_battery_clock.update(grid is GridState.ON_BATTERY, now),
            socket_dead_for=self._socket_dead_clock.update(ups is not None and not ups.mains_present, now),
        )
