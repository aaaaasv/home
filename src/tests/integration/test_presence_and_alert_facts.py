from datetime import datetime, timezone

from src.bot.handlers.air_alert.facts import gather_facts as gather_air_alert_facts
from src.bot.handlers.presence.facts import gather_facts as gather_presence_facts
from src.bot.services.household_facts import FactsContext
from src.common.config import Settings
from src.infrastructure.db.uow import UnitOfWork
from src.tests.integration.base import BaseIntegrationTestCase

FIRST_PHONE = "00:00:5E:00:53:01"
SECOND_PHONE = "00:00:5E:00:53:02"


class PresenceAndAlertFactsTestCase(BaseIntegrationTestCase):
    """
    The assistant answers «о котрій ми вчора прийшли» and «чому вночі горіло світло» from the journals written for it.

    both journals record a reason with every entry, and the reason is the whole answer — a bare timestamp would only
    say that something happened, which the person asking already knows.
    """

    def build_context(self) -> FactsContext:
        return FactsContext(
            household_calendar=self.household_calendar,
            uow_factory=lambda: UnitOfWork(session_factory=self.session_factory),
            settings=Settings(TELEGRAM_BOT_TOKEN="123:abc"),
        )

    async def seed_presence(self, mac: str, event: str, moment: datetime, outcome: str | None = None) -> None:
        async with self.uow as uow:
            await uow.presence_events.create({"mac": mac, "event": event, "outcome": outcome, "at": moment})

    async def seed_alert(self, level: str, moment: datetime, **overrides) -> None:
        async with self.uow as uow:
            await uow.air_alert_events.create({"level": level, "at": moment, **overrides})

    async def test_gather_presence_facts_with_no_events_says_nothing(self):
        context = self.build_context()

        facts = await gather_presence_facts(context)

        self.assertEqual(facts, "")

    async def test_gather_presence_facts_gives_each_arrival_its_local_time_and_the_light_decision(self):
        await self.seed_presence(FIRST_PHONE, "left", datetime(2026, 7, 11, 15, 0, tzinfo=timezone.utc))
        await self.seed_presence(FIRST_PHONE, "joined", datetime(2026, 7, 11, 19, 41, tzinfo=timezone.utc), "raised")
        await self.seed_presence(
            SECOND_PHONE, "joined", datetime(2026, 7, 11, 19, 42, tzinfo=timezone.utc), "somebody_home"
        )
        context = self.build_context()

        facts = await gather_presence_facts(context)

        self.assertEqual(
            facts.splitlines()[1:],
            [
                "— 2026-07-11 18:00: телефон 1 зник із Wi-Fi",
                "— 2026-07-11 22:41: телефон 1 зайшов у Wi-Fi (підсвітку в передпокої увімкнув)",
                "— 2026-07-11 22:42: телефон 2 зайшов у Wi-Fi (підсвітку не вмикав: хтось уже був удома)",
            ],
        )

    async def test_gather_presence_facts_never_shows_a_hardware_address(self):
        await self.seed_presence(FIRST_PHONE, "joined", datetime(2026, 7, 11, 19, 41, tzinfo=timezone.utc), "hop")
        context = self.build_context()

        facts = await gather_presence_facts(context)

        self.assertNotIn(FIRST_PHONE, facts)

    async def test_gather_presence_facts_leaves_out_events_older_than_three_days(self):
        await self.seed_presence(FIRST_PHONE, "joined", datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc), "raised")
        await self.seed_presence(FIRST_PHONE, "left", datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc))
        context = self.build_context()

        facts = await gather_presence_facts(context)

        self.assertEqual(facts.splitlines()[1:], ["— 2026-07-11 15:00: телефон 1 зник із Wi-Fi"])

    async def test_gather_air_alert_facts_with_no_events_says_nothing(self):
        context = self.build_context()

        facts = await gather_air_alert_facts(context)

        self.assertEqual(facts, "")

    async def test_gather_air_alert_facts_names_the_level_the_reason_and_the_feed(self):
        await self.seed_alert(
            "red",
            datetime(2026, 7, 11, 23, 12, tzinfo=timezone.utc),
            reason="ракетна небезпека",
            outcome="raised",
            source="socket",
        )
        await self.seed_alert(
            "none", datetime(2026, 7, 12, 0, 30, tzinfo=timezone.utc), outcome="cleared", source="poll"
        )
        context = self.build_context()

        facts = await gather_air_alert_facts(context)

        self.assertEqual(
            facts.splitlines()[1:],
            [
                "— 2026-07-12 02:12: червоний рівень — тривога "
                "(початок червоної тривоги, ракетна небезпека, від сокета)",
                "— 2026-07-12 03:30: відбій (кінець червоної тривоги, від опитування)",
            ],
        )

    async def test_gather_air_alert_facts_for_a_yellow_level_with_nothing_else_known_has_no_parentheses(self):
        await self.seed_alert("yellow", datetime(2026, 7, 11, 20, 0, tzinfo=timezone.utc), outcome="unchanged")
        context = self.build_context()

        facts = await gather_air_alert_facts(context)

        self.assertEqual(facts.splitlines()[1:], ["— 2026-07-11 23:00: жовтий рівень — попередження про загрозу"])
