from src.bot.handlers.air_alert.messages import AIR_ALERT_STRIP_OFF_TOAST
from src.modules.lighting.domain import PanelLightState
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.telegram import callback_update

ALERT_TOPIC = 240


class RecordingPanelLight:
    def __init__(self):
        self.state = PanelLightState(is_on=True, brightness_percent=20.0)
        self.asked_for: list[float] = []

    async def read(self) -> PanelLightState | None:
        return self.state

    async def set_brightness(self, brightness_percent: float) -> None:
        self.asked_for.append(brightness_percent)


class AlertCardButtonTestCase(BaseBehaviourTestCase):
    """
    The one button on the alert card, driven through the real dispatcher.

    it lives outside every module topic — the card stands in 🚨 тривога and the strip belongs to ⚡ світло —
    so this is also the test that the callback reaches a handler at all rather than the stale-button answer.
    """

    async def test_the_button_on_an_alert_card_puts_the_strip_out(self):
        strip = RecordingPanelLight()

        await self.feed(callback_update("alertstrip", topic=ALERT_TOPIC), panel_light=strip)

        self.assertEqual(strip.asked_for, [0])

    async def test_the_button_on_an_alert_card_leaves_the_card_saying_what_it_said(self):
        """The card is the record of the alert: /light redraws its own card, and this one must not."""
        await self.feed(callback_update("alertstrip", topic=ALERT_TOPIC), panel_light=RecordingPanelLight())

        self.assertEqual(
            [type(call).__name__ for call in self.session.calls],
            ["AnswerCallbackQuery", "EditMessageReplyMarkup"],
        )

    async def test_the_button_on_an_alert_card_says_what_it_did(self):
        await self.feed(callback_update("alertstrip", topic=ALERT_TOPIC), panel_light=RecordingPanelLight())

        self.assertEqual(
            [call.text for call in self.session.calls_named("AnswerCallbackQuery")], [AIR_ALERT_STRIP_OFF_TOAST]
        )
