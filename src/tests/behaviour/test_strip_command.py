from src.bot.handlers.lighting.messages import LIGHT_STRIP_UNREACHABLE
from src.modules.lighting.domain import PanelLightState
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.telegram import POWER_TOPIC, callback_update, message_update


class RecordingPanelLight:
    """The strip as the host service would answer for it, remembering every level it was asked for."""

    def __init__(self, state: PanelLightState | None = None):
        self.state = state if state is not None else PanelLightState(is_on=True, brightness_percent=20.0)
        self.asked_for: list[float] = []

    async def read(self) -> PanelLightState | None:
        return self.state

    async def set_brightness(self, brightness_percent: float) -> None:
        self.asked_for.append(brightness_percent)


class StripCommandTestCase(BaseBehaviourTestCase):
    """
    /light is the hand on the strip for when the home app cannot be reached.

    the night of 13/14.10 is the whole reason it exists: a red alert raised the strip, apple home answered
    from neither band of the wi-fi, and the night ended with somebody on a wardrobe pulling the plug. it is
    fed through the real dispatcher because that is the only thing that proves the strip is actually injected.
    """

    async def test_light_in_the_power_topic_shows_the_level_the_strip_stands_at(self):
        await self.feed(message_update("/light", topic=POWER_TOPIC), panel_light=RecordingPanelLight())

        self.assertEqual(self.session.sent_texts(), ["💡 <b>Стрічка</b> — 20%"])

    async def test_light_with_the_strip_out_says_it_is_not_burning(self):
        strip = RecordingPanelLight(PanelLightState(is_on=False, brightness_percent=0.0))

        await self.feed(message_update("/light", topic=POWER_TOPIC), panel_light=strip)

        self.assertEqual(self.session.sent_texts(), ["🌑 <b>Стрічка</b> — не горить"])

    async def test_light_with_the_host_service_silent_says_so_instead_of_going_quiet(self):
        strip = RecordingPanelLight()
        strip.read = _nothing

        await self.feed(message_update("/light", topic=POWER_TOPIC), panel_light=strip)

        self.assertEqual(self.session.sent_texts(), [LIGHT_STRIP_UNREACHABLE])

    async def test_the_off_button_puts_the_strip_out(self):
        strip = RecordingPanelLight()

        await self.feed(callback_update("strip:0", topic=POWER_TOPIC), panel_light=strip)

        self.assertEqual(strip.asked_for, [0])

    async def test_a_level_button_sets_the_level_it_names(self):
        strip = RecordingPanelLight()

        await self.feed(callback_update("strip:50", topic=POWER_TOPIC), panel_light=strip)

        self.assertEqual(strip.asked_for, [50])


async def _nothing():
    return None
