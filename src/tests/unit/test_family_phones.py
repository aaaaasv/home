import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.modules.presence.domain import NetworkClient
from src.modules.presence.services.family_phones import FamilyPhones
from src.tests.fakes import FrozenHouseholdCalendar

PHONE = "00:00:5E:00:53:01"
ROTATED = "00:00:5E:00:53:0A"
LAPTOP = "00:00:5E:00:53:F0"
NOW = datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc)


class CountingRouter:
    def __init__(self, clients):
        self.clients = clients
        self.reachable = True
        self.reads = 0

    async def read_clients(self):
        self.reads += 1
        return self.clients if self.reachable else None


class FamilyPhonesTestCase(unittest.IsolatedAsyncioTestCase):
    """
    The counting is the point: whether an address is ours is asked of every event the router's log emits, and
    one misbehaving neighbouring device reassociates twice a second.
    """

    def setUp(self):
        self.household_calendar = FrozenHouseholdCalendar(timezone=ZoneInfo("Europe/Kyiv"), frozen_now=NOW)
        self.router = CountingRouter(
            [
                NetworkClient(mac=PHONE, name="iPhone", is_online=True),
                NetworkClient(mac=LAPTOP, name="MacBookPro", is_online=True),
            ]
        )

    def build_family_phones(self, phone_macs=frozenset()) -> FamilyPhones:
        return FamilyPhones(
            presence_source=self.router,
            phone_names={"iPhone"},
            phone_macs=set(phone_macs),
            household_calendar=self.household_calendar,
            recognition_minutes=10,
        )

    async def test_recognises_a_phone_by_the_name_the_router_knows_it_by(self):
        family_phones = self.build_family_phones()

        recognised = await family_phones.recognises(PHONE)

        self.assertTrue(recognised)

    async def test_recognises_rejects_a_client_the_router_names_something_else(self):
        family_phones = self.build_family_phones()

        recognised = await family_phones.recognises(LAPTOP)

        self.assertFalse(recognised)

    async def test_recognises_a_known_address_repeatedly_without_asking_the_router_again(self):
        family_phones = self.build_family_phones()
        await family_phones.recognises(PHONE)

        for _ in range(50):
            await family_phones.recognises(LAPTOP)

        self.assertEqual(self.router.reads, 1)

    async def test_recognises_asks_the_router_again_for_an_address_never_seen_before(self):
        """A rotated address arrives as a stranger, and waiting for the clock would miss the arrival."""
        family_phones = self.build_family_phones()
        await family_phones.recognises(PHONE)
        self.router.clients = self.router.clients + [NetworkClient(mac=ROTATED, name="iPhone", is_online=True)]

        recognised = await family_phones.recognises(ROTATED)

        self.assertTrue(recognised)
        self.assertEqual(self.router.reads, 2)

    async def test_recognises_asks_the_router_again_once_the_remembered_roster_has_aged_out(self):
        family_phones = self.build_family_phones()
        await family_phones.recognises(PHONE)
        self.household_calendar.frozen_now += timedelta(minutes=11)

        await family_phones.recognises(PHONE)

        self.assertEqual(self.router.reads, 2)

    async def test_recognises_keeps_the_remembered_answer_when_the_router_stops_answering(self):
        """Which phone wears which name changes far more slowly than the router's reachability."""
        family_phones = self.build_family_phones()
        await family_phones.recognises(PHONE)
        self.household_calendar.frozen_now += timedelta(minutes=11)
        self.router.reachable = False

        recognised = await family_phones.recognises(PHONE)

        self.assertTrue(recognised)

    async def test_recognises_is_unsure_when_the_router_has_never_been_reached(self):
        family_phones = self.build_family_phones()
        self.router.reachable = False

        recognised = await family_phones.recognises(PHONE)

        self.assertIsNone(recognised)

    async def test_recognises_an_explicitly_configured_address_without_asking_the_router(self):
        family_phones = self.build_family_phones(phone_macs={LAPTOP.lower()})

        recognised = await family_phones.recognises(LAPTOP)

        self.assertTrue(recognised)
        self.assertEqual(self.router.reads, 0)

    async def test_read_roster_reports_who_is_on_the_wifi_among_our_phones(self):
        family_phones = self.build_family_phones()

        roster = await family_phones.read_roster()

        self.assertEqual(roster.ours, frozenset({PHONE}))
        self.assertEqual(roster.online, frozenset({PHONE, LAPTOP}))
        self.assertEqual(roster.known, frozenset({PHONE, LAPTOP}))

    async def test_read_roster_returns_nothing_when_the_router_cannot_be_reached(self):
        family_phones = self.build_family_phones()
        self.router.reachable = False

        roster = await family_phones.read_roster()

        self.assertIsNone(roster)
