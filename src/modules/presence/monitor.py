from datetime import datetime, timedelta


class PresenceMonitor:
    """
    Decides the moment the last family phone has left.

    a grace window rides through the brief drops a phone makes when it deep-sleeps, so "everyone away" means
    genuinely gone, not screen-off. state is in memory and re-seeds from the first reading after a restart, so a
    deploy cannot fire a spurious "everyone left". it reports only the present -> away edge, once per departure.
    """

    def __init__(self, family_macs: set[str], away_grace: timedelta):
        self.family_macs = {mac.upper() for mac in family_macs}
        self.away_grace = away_grace
        self._last_seen: dict[str, datetime] = {}
        self._everyone_away: bool | None = None

    def update(self, online_macs: set[str], moment: datetime) -> bool:
        online = {mac.upper() for mac in online_macs}
        for mac in self.family_macs & online:
            self._last_seen[mac] = moment

        someone_present = any(
            mac in self._last_seen and moment - self._last_seen[mac] < self.away_grace for mac in self.family_macs
        )
        everyone_away = not someone_present

        just_left = self._everyone_away is False and everyone_away
        self._everyone_away = everyone_away
        return just_left
