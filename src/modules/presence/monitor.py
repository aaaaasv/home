from datetime import datetime, timedelta

from src.modules.presence.domain import PhoneRoster


class PresenceMonitor:
    """
    Decides the moment the last family phone has left.

    a grace window rides through the brief drops a phone makes when it deep-sleeps, so "everyone away" means
    genuinely gone, not screen-off. state is in memory and re-seeds from the first reading after a restart, so a
    deploy cannot fire a spurious "everyone left". it reports only the present -> away edge, once per departure.

    the same window covers the other way a phone disappears: ios retiring one private address for a new one looks
    exactly like leaving and arriving, and riding through it is the correct reading — the person never moved.
    """

    def __init__(self, away_grace: timedelta):
        self.away_grace = away_grace
        self._last_seen: dict[str, datetime] = {}
        self._everyone_away: bool | None = None

    def update(self, roster: PhoneRoster, moment: datetime) -> bool:
        for mac in roster.ours & roster.online:
            self._last_seen[mac] = moment
        # an address ages out rather than being dropped the moment the router stops listing it: a client list
        # that comes back short for one read must not be read as the flat emptying
        self._last_seen = {mac: seen for mac, seen in self._last_seen.items() if moment - seen < self.away_grace}

        everyone_away = not self._last_seen

        just_left = self._everyone_away is False and everyone_away
        self._everyone_away = everyone_away
        return just_left
