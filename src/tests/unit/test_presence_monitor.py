import unittest
from datetime import datetime, timedelta, timezone

from src.modules.presence.domain import PhoneRoster
from src.modules.presence.monitor import PresenceMonitor

PHONE_A = "00:00:5E:00:53:01"
PHONE_B = "00:00:5E:00:53:02"
ROTATED_A = "00:00:5E:00:53:0A"
GRACE = timedelta(minutes=15)
START = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return START + timedelta(minutes=minutes)


def roster(online: set[str], ours: set[str] | None = None) -> PhoneRoster:
    recognised = ours if ours is not None else {PHONE_A, PHONE_B}
    return PhoneRoster(ours=frozenset(recognised), online=frozenset(online), known=frozenset(recognised | online))


class PresenceMonitorTestCase(unittest.TestCase):
    def build_monitor(self) -> PresenceMonitor:
        return PresenceMonitor(away_grace=GRACE)

    def test_update_seeds_the_first_reading_without_firing(self):
        monitor = self.build_monitor()

        fired = monitor.update(roster({PHONE_A, PHONE_B}), at(0))

        self.assertFalse(fired)

    def test_update_fires_once_after_the_last_phone_is_gone_past_the_grace(self):
        monitor = self.build_monitor()
        monitor.update(roster({PHONE_A, PHONE_B}), at(0))
        self.assertFalse(monitor.update(roster(set()), at(5)))
        self.assertFalse(monitor.update(roster(set()), at(14)))

        fired = monitor.update(roster(set()), at(16))

        self.assertTrue(fired)

    def test_update_does_not_refire_while_everyone_stays_away(self):
        monitor = self.build_monitor()
        monitor.update(roster({PHONE_A, PHONE_B}), at(0))
        monitor.update(roster(set()), at(16))

        fired = monitor.update(roster(set()), at(30))

        self.assertFalse(fired)

    def test_update_stays_silent_when_a_phone_returns_within_the_grace(self):
        monitor = self.build_monitor()
        monitor.update(roster({PHONE_A, PHONE_B}), at(0))
        monitor.update(roster(set()), at(10))

        fired = monitor.update(roster({PHONE_A}), at(12))

        self.assertFalse(fired)

    def test_update_stays_silent_while_one_phone_is_still_home(self):
        monitor = self.build_monitor()
        monitor.update(roster({PHONE_A, PHONE_B}), at(0))

        fired = monitor.update(roster({PHONE_A}), at(20))

        self.assertFalse(fired)

    def test_update_fires_again_after_someone_returns_and_leaves(self):
        monitor = self.build_monitor()
        monitor.update(roster({PHONE_A, PHONE_B}), at(0))
        monitor.update(roster(set()), at(16))
        monitor.update(roster({PHONE_A, PHONE_B}), at(20))
        monitor.update(roster(set()), at(25))

        fired = monitor.update(roster(set()), at(41))

        self.assertTrue(fired)

    def test_update_rides_through_a_phone_rotating_its_private_address(self):
        """One address retired and another taken up inside the grace window is nobody leaving."""
        monitor = self.build_monitor()
        monitor.update(roster({PHONE_A}, ours={PHONE_A}), at(0))

        fired = monitor.update(roster({ROTATED_A}, ours={PHONE_A, ROTATED_A}), at(3))

        self.assertFalse(fired)

    def test_update_lets_an_address_the_router_forgot_age_out_over_the_grace(self):
        """A client list that comes back short for one read is not the flat emptying — but a retired address
        must not hold it occupied for ever either."""
        monitor = self.build_monitor()
        monitor.update(roster({PHONE_A}, ours={PHONE_A}), at(0))
        self.assertFalse(monitor.update(roster(set(), ours=set()), at(1)))

        fired = monitor.update(roster(set(), ours=set()), at(16))

        self.assertTrue(fired)
