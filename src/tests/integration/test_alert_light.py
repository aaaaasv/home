from src.bot.handlers.air_alert.light import AlertLightWatcher
from src.common.config import Settings
from src.modules.air_alert.domain import AirAlert, AlertLevel
from src.modules.lighting.domain import PanelLightState
from src.tests.integration.base import BaseIntegrationTestCase

ALERT_PERCENT = 20.0


class ScriptedAlertSource:
    """Answers with the levels the test lines up, and with None when the feed is meant to be unreachable."""

    def __init__(self, *levels):
        self.answers = [None if level is None else AirAlert(level=level, reason="Ракетна загроза") for level in levels]

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
            settings=Settings(TELEGRAM_BOT_TOKEN="123:abc", ALERT_LIGHT_PERCENT=ALERT_PERCENT),
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

    async def test_the_all_clear_puts_out_a_light_we_raised(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(ScriptedAlertSource(AlertLevel.RED, AlertLevel.NONE), light)
        await watcher()

        await watcher()

        self.assertEqual(light.asked_for, [ALERT_PERCENT, 0])

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


async def _none():
    return None
