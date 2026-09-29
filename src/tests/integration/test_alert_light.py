from datetime import datetime, timedelta, timezone

from src.bot.handlers.air_alert.light import AlertLightWatcher
from src.common.config import Settings
from src.modules.air_alert.domain import AirAlert, AlertLevel
from src.modules.lighting.domain import PanelLightState
from src.tests.integration.base import BaseIntegrationTestCase

ALERT_PERCENT = 20.0
ALERT_MINUTES = 15
FAR_PAST = datetime(2000, 1, 1, tzinfo=timezone.utc)


class ScriptedAlertSource:
    """Answers with the levels the test lines up, and with None when the feed is meant to be unreachable."""

    def __init__(self, *levels):
        self.answers = [
            None if level is None else AirAlert(level=level, reason="Ракетна загроза", source="socket")
            for level in levels
        ]

    async def read_current(self):
        return self.answers.pop(0) if self.answers else None


class RecordingPanelLight:
    """A strip that remembers what it was asked for, and can pretend somebody else moved it."""

    def __init__(self, state: PanelLightState | None = None):
        self.state = state if state is not None else PanelLightState(is_on=False, brightness_percent=0.0)
        self.asked_for: list[float] = []

    async def read(self) -> PanelLightState | None:
        return self.state

    async def set_brightness(self, brightness_percent: float) -> None:
        self.asked_for.append(brightness_percent)
        self.state = PanelLightState(is_on=brightness_percent > 0, brightness_percent=brightness_percent)


class AlertLightTestCase(BaseIntegrationTestCase):
    """
    What the strip does when the city goes red, and — more importantly — what it refuses to do.

    the refusals are the reason this is safe to leave enabled: an automation that overrides a light somebody
    is already using gets switched off for good, and then it is not there on the night it matters.
    """

    def build_watcher(self, source, light) -> AlertLightWatcher:
        return AlertLightWatcher(
            uow_factory=lambda: self.uow,
            source=source,
            panel_light=light,
            settings=Settings(
                TELEGRAM_BOT_TOKEN="123:abc", ALERT_LIGHT_PERCENT=ALERT_PERCENT, ALERT_LIGHT_MINUTES=ALERT_MINUTES
            ),
            household_calendar=self.household_calendar,
        )

    async def test_a_red_alert_raises_the_light(self):
        light = RecordingPanelLight()

        await self.build_watcher(ScriptedAlertSource(AlertLevel.RED), light)()

        self.assertEqual(light.asked_for, [ALERT_PERCENT])

    async def test_a_yellow_alert_leaves_the_light_alone(self):
        """Yellow runs for hours several nights a week — answering it would get the whole thing disabled."""
        light = RecordingPanelLight()

        await self.build_watcher(ScriptedAlertSource(AlertLevel.YELLOW), light)()

        self.assertEqual(light.asked_for, [])

    async def test_a_red_alert_that_is_already_running_does_not_raise_the_light_twice(self):
        light = RecordingPanelLight()
        await self.build_watcher(ScriptedAlertSource(AlertLevel.RED), light)()

        await self.build_watcher(ScriptedAlertSource(AlertLevel.RED), light)()

        self.assertEqual(light.asked_for, [ALERT_PERCENT])

    async def test_a_red_alert_with_the_light_already_on_leaves_it_where_it_was(self):
        light = RecordingPanelLight(PanelLightState(is_on=True, brightness_percent=55.0))

        await self.build_watcher(ScriptedAlertSource(AlertLevel.RED), light)()

        self.assertEqual(light.asked_for, [])
        self.assertEqual(light.state.brightness_percent, 55.0)

    async def test_the_light_stays_up_while_the_minutes_it_was_raised_for_run(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED, AlertLevel.RED), light)
        await watcher()

        self.household_calendar.frozen_now += timedelta(minutes=ALERT_MINUTES - 1)
        await watcher()

        self.assertEqual(light.asked_for, [ALERT_PERCENT])

    async def test_the_light_goes_out_on_the_clock_even_with_the_alert_still_running(self):
        """It is there for putting shoes on and getting out; an alert can run for hours after that is done."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED, AlertLevel.RED), light)
        await watcher()

        self.household_calendar.frozen_now += timedelta(minutes=ALERT_MINUTES + 1)
        await watcher()

        self.assertEqual(light.asked_for, [ALERT_PERCENT, 0])

    async def test_the_all_clear_alone_does_not_put_the_light_out(self):
        """The clock owns the lowering now, so an all-clear a minute in leaves the light where it is."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED, AlertLevel.NONE), light)
        await watcher()

        self.household_calendar.frozen_now += timedelta(minutes=1)
        await watcher()

        self.assertEqual(light.asked_for, [ALERT_PERCENT])

    async def test_the_all_clear_leaves_a_light_somebody_else_moved(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED, AlertLevel.NONE), light)
        await watcher()
        light.state = PanelLightState(is_on=True, brightness_percent=70.0)

        await watcher()

        self.assertEqual(light.asked_for, [ALERT_PERCENT])
        self.assertEqual(light.state.brightness_percent, 70.0)

    async def test_the_all_clear_does_not_touch_a_light_this_bot_never_raised(self):
        """An alert that began before the bot started is not ours to end."""
        light = RecordingPanelLight(PanelLightState(is_on=True, brightness_percent=30.0))

        await self.build_watcher(ScriptedAlertSource(AlertLevel.NONE), light)()

        self.assertEqual(light.asked_for, [])

    async def test_an_unreachable_feed_changes_nothing(self):
        """An unknown level is not an all-clear — whatever is raised stays raised until we actually hear."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED, None), light)
        await watcher()

        await watcher()

        self.assertEqual(light.asked_for, [ALERT_PERCENT])

    async def test_a_red_alert_with_no_light_service_answering_is_survived(self):
        light = RecordingPanelLight()
        light.read = lambda: _none()

        await self.build_watcher(ScriptedAlertSource(AlertLevel.RED), light)()

        self.assertEqual(light.asked_for, [])

    async def test_a_second_red_while_the_light_is_up_does_not_touch_it(self):
        """The night of 29.09: a «new» red arrived mid-alert and the light came up again at two in the morning."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED, AlertLevel.YELLOW, AlertLevel.RED), light)
        await watcher()
        await watcher()

        await watcher()

        self.assertEqual(light.asked_for, [ALERT_PERCENT])

    async def test_every_change_of_level_is_written_to_the_journal(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(
            ScriptedAlertSource(AlertLevel.RED, AlertLevel.RED, AlertLevel.YELLOW, AlertLevel.NONE), light
        )
        for _ in range(4):
            await watcher()

        async with self.uow as uow:
            journal = await uow.air_alert_events.list_since(FAR_PAST)
        self.assertEqual([event.level for event in journal], ["red", "yellow", "none"])
        self.assertEqual([event.outcome for event in journal], ["raised", "cleared", "unchanged"])

    async def test_the_journal_records_which_feed_answered(self):
        """Two feeds disagreeing is this module's one real failure, and it cannot be told apart without this."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED), light)

        await watcher()

        async with self.uow as uow:
            journal = await uow.air_alert_events.list_since(FAR_PAST)
        self.assertEqual([event.source for event in journal], ["socket"])


async def _none():
    return None
