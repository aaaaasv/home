import unittest
from datetime import datetime, timedelta, timezone

from src.modules.presence.monitor import PresenceMonitor

PHONE_A = "00:00:5E:00:53:01"
PHONE_B = "00:00:5E:00:53:02"
GRACE = timedelta(minutes=15)
START = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return START + timedelta(minutes=minutes)


class PresenceMonitorTestCase(unittest.TestCase):
    def build_monitor(self) -> PresenceMonitor:
        return PresenceMonitor(family_macs={PHONE_A, PHONE_B}, away_grace=GRACE)

    def test_update_seeds_the_first_reading_without_firing(self):
        monitor = self.build_monitor()

        fired = monitor.update({PHONE_A, PHONE_B}, at(0))

        self.assertFalse(fired)

    def test_update_fires_once_after_the_last_phone_is_gone_past_the_grace(self):
        monitor = self.build_monitor()
        monitor.update({PHONE_A, PHONE_B}, at(0))
        self.assertFalse(monitor.update(set(), at(5)))
        self.assertFalse(monitor.update(set(), at(14)))

        fired = monitor.update(set(), at(16))

        self.assertTrue(fired)

    def test_update_does_not_refire_while_everyone_stays_away(self):
        monitor = self.build_monitor()
        monitor.update({PHONE_A, PHONE_B}, at(0))
        monitor.update(set(), at(16))

        fired = monitor.update(set(), at(30))

        self.assertFalse(fired)

    def test_update_stays_silent_when_a_phone_returns_within_the_grace(self):
        monitor = self.build_monitor()
        monitor.update({PHONE_A, PHONE_B}, at(0))
        monitor.update(set(), at(10))

        fired = monitor.update({PHONE_A}, at(12))

        self.assertFalse(fired)

    def test_update_stays_silent_while_one_phone_is_still_home(self):
        monitor = self.build_monitor()
        monitor.update({PHONE_A, PHONE_B}, at(0))

        fired = monitor.update({PHONE_A}, at(20))

        self.assertFalse(fired)

    def test_update_fires_again_after_someone_returns_and_leaves(self):
        monitor = self.build_monitor()
        monitor.update({PHONE_A, PHONE_B}, at(0))
        monitor.update(set(), at(16))
        monitor.update({PHONE_A, PHONE_B}, at(20))
        monitor.update(set(), at(25))

        fired = monitor.update(set(), at(41))

        self.assertTrue(fired)

    def test_update_ignores_the_case_of_a_mac(self):
        monitor = self.build_monitor()

        fired = monitor.update({PHONE_A.lower(), PHONE_B.lower()}, at(0))

        self.assertFalse(fired)
        self.assertFalse(monitor.update({PHONE_A.lower()}, at(20)))
