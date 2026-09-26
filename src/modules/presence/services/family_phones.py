"""Deciding which addresses on the wi-fi belong to the family, and doing it cheaply enough to ask every time."""
import logging
from datetime import timedelta

from src.common.household_calendar import HouseholdCalendar
from src.modules.presence.domain import NetworkClient, PhoneRoster
from src.modules.presence.services.presence_source import PresenceSource

logger = logging.getLogger(__name__)


class FamilyPhones:
    """
    Answers «чи це наш телефон» by the name the router knows, so a rotated address costs nothing.

    two questions with different appetites, hence two methods. whether an address is ours is asked of every
    single event the router's log produces — one misbehaving neighbour's device reassociates twice a second, so
    that answer has to come from memory. whether somebody else is home decides a light, is asked only for our
    own arrivals, and must be current, so that one always goes to the router.

    the remembered classification is re-read when it ages out **or when an address turns up that has never been
    seen before** — which is precisely how a rotated address arrives, and the one case where waiting for the
    clock would mean missing the arrival it was built for.
    """

    def __init__(
        self,
        presence_source: PresenceSource,
        phone_names: set[str],
        phone_macs: set[str],
        household_calendar: HouseholdCalendar,
        recognition_minutes: int,
    ):
        self.presence_source = presence_source
        self.phone_names = {name.casefold() for name in phone_names if name}
        self.phone_macs = frozenset(mac.upper() for mac in phone_macs)
        self.household_calendar = household_calendar
        self.recognition_minutes = recognition_minutes
        self._ours: frozenset[str] = frozenset()
        self._known: frozenset[str] = frozenset()
        self._read_at = None

    async def recognises(self, mac: str) -> bool | None:
        """Whether this address is one of the family's phones — None only when the router was never reached."""
        if mac in self.phone_macs:
            return True
        if self._should_reread(mac) and await self.read_roster() is None and self._read_at is None:
            # a stale answer beats no answer: which phone wears which name changes far more slowly than
            # the router's reachability, so an outage must not make the flat forget whose phone this is
            return None
        return mac in self._ours

    async def read_roster(self) -> PhoneRoster | None:
        """Ask the router who it knows and who is on the wi-fi right now, and remember the classification."""
        clients = await self.presence_source.read_clients()
        if clients is None:
            return None

        roster = PhoneRoster(
            ours=frozenset(client.mac for client in clients if self._is_ours(client)) | self.phone_macs,
            online=frozenset(client.mac for client in clients if client.is_online),
            known=frozenset(client.mac for client in clients),
        )
        if roster.ours != self._ours and self._read_at is not None:
            logger.info("The family phones the router recognises changed: %d now", len(roster.ours))
        self._ours = roster.ours
        self._known = roster.known
        self._read_at = self.household_calendar.now()
        return roster

    def _should_reread(self, mac: str) -> bool:
        if self._read_at is None:
            return True
        if mac not in self._known:
            return True
        return self.household_calendar.now() - self._read_at >= timedelta(minutes=self.recognition_minutes)

    def _is_ours(self, client: NetworkClient) -> bool:
        if client.mac in self.phone_macs:
            return True
        name = (client.name or "").casefold()
        return any(wanted in name for wanted in self.phone_names)
