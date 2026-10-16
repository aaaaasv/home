from datetime import datetime, timedelta, timezone

from src.bot.handlers.air_alert.announcement import AlertAnnouncement
from src.bot.handlers.air_alert.light import AlertLight
from src.bot.handlers.air_alert.watcher import AirAlertWatcher
from src.bot.services.posted_message_tracker import AIR_ALERT_CARD_KIND
from src.common.config import Settings
from src.modules.air_alert.domain import AirAlert, AlertLevel
from src.modules.lighting.domain import PanelLightState
from src.tests.fakes import RecordingBot, StubForumTopic
from src.tests.integration.base import BaseIntegrationTestCase

CHAT_ID = -1001234567890
ALERT_TOPIC = 240
ALERT_PERCENT = 20.0
RED = "Ракетна загроза (червоний рівень)"
YELLOW = "Дронова загроза (жовтий рівень)"


class ScriptedAlertSource:
    """Answers with the levels the test lines up, each with the reason the official map gives it."""

    def __init__(self, *levels):
        reasons = {AlertLevel.RED: RED, AlertLevel.YELLOW: YELLOW, AlertLevel.NONE: None}
        self.answers = [AirAlert(level=level, reason=reasons[level], source="socket") for level in levels]

    async def read_current(self):
        return self.answers.pop(0) if self.answers else None


class RecordingPanelLight:
    def __init__(self, state: PanelLightState | None = None):
        self.state = state if state is not None else PanelLightState(is_on=False, brightness_percent=0.0)
        self.asked_for: list[float] = []
        self.leases: list[tuple[float, float | None]] = []

    async def read(self) -> PanelLightState | None:
        return self.state

    async def set_brightness(self, brightness_percent: float, minutes: float | None = None) -> None:
        self.leases.append((brightness_percent, minutes))
        self.asked_for.append(brightness_percent)
        self.state = PanelLightState(is_on=brightness_percent > 0, brightness_percent=brightness_percent)


class AlertAnnouncementTestCase(BaseIntegrationTestCase):
    """
    The card in 🚨 тривога: one per red alert, pinged once, then written over where it stands.

    the feed reaches this bot before the siren is audible and before any channel has posted, and until this
    card existed the only thing it told was a strip on the switchboard that nobody was looking at.
    """

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.bot = RecordingBot()
        self.light = RecordingPanelLight()

    def build_announcement(self) -> AlertAnnouncement:
        return AlertAnnouncement(
            bot=self.bot,
            chat_id=CHAT_ID,
            alert_topic=StubForumTopic(ALERT_TOPIC),
            uow_factory=lambda: self.uow,
            household_calendar=self.household_calendar,
        )

    def build_watcher(self, source, with_strip: bool = True) -> AirAlertWatcher:
        return AirAlertWatcher(
            uow_factory=lambda: self.uow,
            source=source,
            household_calendar=self.household_calendar,
            light=(
                AlertLight(
                    panel_light=self.light,
                    settings=Settings(TELEGRAM_BOT_TOKEN="123:abc", ALERT_LIGHT_PERCENT=ALERT_PERCENT),
                    household_calendar=self.household_calendar,
                )
                if with_strip
                else None
            ),
            announcement=self.build_announcement(),
        )

    async def test_call_on_a_red_alert_pushes_one_card_into_the_alert_topic(self):
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED))

        await watcher()

        self.assertEqual(
            [(call["message_thread_id"], call["text"], call["silent"]) for call in self.bot.sent],
            [(ALERT_TOPIC, f"🚨 <b>Червона тривога</b>\n\n{RED}\n\n<i>о 09:00</i>", False)],
        )

    async def test_call_on_a_red_alert_that_raised_the_strip_offers_to_put_it_out(self):
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED))

        await watcher()

        self.assertEqual(
            [button.text for row in self.bot.sent[0]["reply_markup"].inline_keyboard for button in row],
            ["Погасити стрічку"],
        )

    async def test_call_on_a_red_alert_with_the_strip_left_as_the_family_set_it_offers_nothing(self):
        """Offering to put out a light somebody chose themselves is how an automation earns its reputation."""
        self.light.state = PanelLightState(is_on=True, brightness_percent=70.0)
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED))

        await watcher()

        self.assertEqual([call.get("reply_markup") for call in self.bot.sent], [None])

    async def test_call_on_a_red_alert_with_no_strip_at_all_still_pushes_the_card(self):
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED), with_strip=False)

        await watcher()

        self.assertEqual(
            [(call["text"].splitlines()[0], call.get("reply_markup")) for call in self.bot.sent],
            [("🚨 <b>Червона тривога</b>", None)],
        )

    async def test_call_on_a_yellow_alert_says_nothing(self):
        """Sixty-five yellow warnings in a fortnight against seven reds — a topic that speaks for them gets muted."""
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.YELLOW))

        await watcher()

        self.assertEqual(self.bot.sent, [])

    async def test_call_when_the_red_drops_to_yellow_writes_over_the_card_with_what_is_left(self):
        """«Відбій» here would send somebody out of the corridor while the drones are still coming."""
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED, AlertLevel.YELLOW))
        await watcher()
        self.household_calendar.frozen_now += timedelta(hours=1, minutes=11)

        await watcher()

        self.assertEqual(
            [(edit["message_id"], edit["text"]) for edit in self.bot.edited],
            [(500, f"🟡 <b>Червону знято</b>\n\n{YELLOW}\n\n<i>тривала 1 год 11 хв · 09:00–10:11</i>")],
        )

    async def test_call_when_the_alert_is_fully_over_writes_over_the_card_with_the_all_clear(self):
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED, AlertLevel.NONE))
        await watcher()
        self.household_calendar.frozen_now += timedelta(minutes=40)

        await watcher()

        self.assertEqual(
            [edit["text"] for edit in self.bot.edited],
            ["✅ <b>Відбій</b>\n\n<i>тривала 40 хв · 09:00–09:40</i>"],
        )

    async def test_call_when_the_alert_ends_sends_no_second_message(self):
        """A second push to say the red is off is how the topic that must beat the siren gets muted."""
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED, AlertLevel.NONE))
        await watcher()

        await watcher()

        self.assertEqual(len(self.bot.sent), 1)

    async def test_call_when_the_alert_ends_after_a_restart_still_writes_over_the_card(self):
        """The card and the minute it went up are in the database, because an alert outlives a deploy."""
        await self.build_watcher(ScriptedAlertSource(AlertLevel.RED))()
        self.household_calendar.frozen_now += timedelta(minutes=25)

        await self.build_watcher(ScriptedAlertSource(AlertLevel.NONE))()

        self.assertEqual(
            [(edit["message_id"], edit["text"]) for edit in self.bot.edited],
            [(500, "✅ <b>Відбій</b>\n\n<i>тривала 25 хв · 09:00–09:25</i>")],
        )

    async def test_call_when_a_red_ends_that_began_before_the_bot_did_writes_over_nothing(self):
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED))
        async with self.uow as uow:
            await uow.air_alert_state.save(level=AlertLevel.RED, reason=RED, changed_at=self.household_calendar.now())

        await watcher()

        self.assertEqual((self.bot.sent, self.bot.edited), ([], []))

    async def test_call_on_a_second_red_leaves_the_earlier_card_standing(self):
        """Each card is the record of its own night, so the lane is forgotten rather than cleared."""
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED, AlertLevel.NONE, AlertLevel.RED))
        await watcher()
        await watcher()

        await watcher()

        self.assertEqual(self.bot.deleted, [])
        async with self.uow as uow:
            tracked = await uow.posted_messages.list_by_kind(AIR_ALERT_CARD_KIND)
        self.assertEqual([posted.message_id for posted in tracked], [501])

    async def test_call_on_a_red_alert_remembers_the_minute_it_was_raised(self):
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED))

        await watcher()

        async with self.uow as uow:
            tracked = await uow.posted_messages.list_by_kind(AIR_ALERT_CARD_KIND)
        self.assertEqual(
            [(posted.message_id, posted.reference) for posted in tracked],
            [(500, datetime(2026, 7, 12, 6, 0, tzinfo=timezone.utc).isoformat())],
        )
