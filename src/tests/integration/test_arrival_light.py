import json
from datetime import datetime, timedelta, timezone

from src.bot.handlers.presence.arrival import ArrivalLightWatcher
from src.common.config import Settings
from src.modules.lighting.domain import PanelLightState
from src.modules.presence.domain import NetworkClient
from src.modules.presence.services.family_phones import FamilyPhones
from src.tests.integration.base import BaseIntegrationTestCase

# 22:00 in Kyiv in late September — the sun is eleven degrees down, which is properly dark
NIGHT = datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc)
# and 13:00 local on the same day, which is not
DAY = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)

MY_PHONE = "AA:BB:CC:DD:EE:01"
OTHER_PHONE = "AA:BB:CC:DD:EE:02"
# the address the same phone takes up after ios retires the one above
ROTATED_PHONE = "AA:BB:CC:DD:EE:0A"
LAPTOP = "AA:BB:CC:DD:EE:F0"
ARRIVAL_PERCENT = 20.0
AWAY_MINUTES = 30


class RecordingPanelLight:
    def __init__(self, state: PanelLightState | None = None):
        self.state = state if state is not None else PanelLightState(is_on=False, brightness_percent=0.0)
        self.asked_for: list[float] = []

    async def read(self):
        return self.state

    async def set_brightness(self, brightness_percent: float) -> None:
        self.asked_for.append(brightness_percent)
        self.state = PanelLightState(is_on=brightness_percent > 0, brightness_percent=brightness_percent)


class ScriptedRouter:
    """The router's client list, which names a phone whatever address it happens to wear."""

    def __init__(self, online):
        self.online = online
        self.reachable = True
        self.reads = 0

    async def read_clients(self):
        self.reads += 1
        if not self.reachable:
            return None
        return [
            NetworkClient(mac=MY_PHONE, name="iPhone", is_online=MY_PHONE in self.online),
            NetworkClient(mac=OTHER_PHONE, name="iPhone", is_online=OTHER_PHONE in self.online),
            NetworkClient(mac=ROTATED_PHONE, name="iPhone", is_online=ROTATED_PHONE in self.online),
            NetworkClient(mac=LAPTOP, name="MacBookPro", is_online=True),
        ]


class ArrivalLightTestCase(BaseIntegrationTestCase):
    """
    Meeting somebody at the door — and, more to the point, every case where it refuses to.

    the refusals are the reason this can stay switched on: the router's own log shows a phone leaving and
    rejoining inside six seconds, so a rule that simply answered «з'явився» would blink all day.

    every one of them is written down, because «чи не вмикалось воно саме, поки нас не було» has to be a
    query rather than a matter of trust.
    """

    def build_watcher(self, light, online=frozenset(), now=NIGHT) -> ArrivalLightWatcher:
        self.household_calendar.frozen_now = now
        self.router = ScriptedRouter(online)
        settings = Settings(
            TELEGRAM_BOT_TOKEN="123:abc",
            PRESENCE_PHONE_NAMES="iPhone",
            PRESENCE_LATITUDE=50.45,
            PRESENCE_LONGITUDE=30.52,
            ARRIVAL_LIGHT_PERCENT=ARRIVAL_PERCENT,
            ARRIVAL_AWAY_MINUTES=AWAY_MINUTES,
            ARRIVAL_LIGHT_MINUTES=10,
        )
        return ArrivalLightWatcher(
            uow_factory=lambda: self.uow,
            panel_light=light,
            family_phones=FamilyPhones(
                presence_source=self.router,
                phone_names=settings.presence_phone_names,
                phone_macs=settings.presence_phone_macs,
                household_calendar=self.household_calendar,
                recognition_minutes=10,
            ),
            settings=settings,
            household_calendar=self.household_calendar,
        )

    async def leave_then_return(self, watcher, away_minutes: int, mac: str = MY_PHONE) -> None:
        watcher.household_calendar.frozen_now -= timedelta(minutes=away_minutes)
        await watcher.handle(json.dumps({"mac": mac, "event": "left"}))
        watcher.household_calendar.frozen_now += timedelta(minutes=away_minutes)
        await watcher.handle(json.dumps({"mac": mac, "event": "joined"}))

    async def outcomes(self) -> list[str | None]:
        async with self.uow as uow:
            events = await uow.presence_events.list_since(datetime(2000, 1, 1, tzinfo=timezone.utc))
        return [event.outcome for event in events if event.event == "joined"]

    async def test_coming_home_after_a_real_absence_in_the_dark_raises_the_light(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)

        await self.leave_then_return(watcher, away_minutes=120)

        self.assertEqual(light.asked_for, [ARRIVAL_PERCENT])
        self.assertEqual(await self.outcomes(), ["raised"])

    async def test_an_absence_measured_across_a_restart_still_counts(self):
        """The departure lives in the database, so a deploy between leaving and returning changes nothing."""
        light = RecordingPanelLight()
        first = self.build_watcher(light)
        first.household_calendar.frozen_now -= timedelta(minutes=120)
        await first.handle(json.dumps({"mac": MY_PHONE, "event": "left"}))

        restarted = self.build_watcher(light)
        await restarted.handle(json.dumps({"mac": MY_PHONE, "event": "joined"}))

        self.assertEqual(light.asked_for, [ARRIVAL_PERCENT])

    async def test_a_phone_hopping_between_bands_is_not_an_arrival(self):
        """The real log shows six seconds between leaving and rejoining — that is a radio, not a person."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)

        watcher.household_calendar.frozen_now -= timedelta(seconds=6)
        await watcher.handle(json.dumps({"mac": MY_PHONE, "event": "left"}))
        watcher.household_calendar.frozen_now += timedelta(seconds=6)
        await watcher.handle(json.dumps({"mac": MY_PHONE, "event": "joined"}))

        self.assertEqual(light.asked_for, [])
        self.assertEqual(await self.outcomes(), ["hop"])

    async def test_coming_home_in_daylight_leaves_the_light_off(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light, now=DAY)

        await self.leave_then_return(watcher, away_minutes=120)

        self.assertEqual(light.asked_for, [])
        self.assertEqual(await self.outcomes(), ["daylight"])

    async def test_coming_home_to_a_flat_that_is_not_empty_leaves_the_light_off(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light, online={OTHER_PHONE})

        await self.leave_then_return(watcher, away_minutes=120)

        self.assertEqual(light.asked_for, [])
        self.assertEqual(await self.outcomes(), ["somebody_home"])

    async def test_coming_home_to_a_light_already_on_leaves_it_where_it_was(self):
        light = RecordingPanelLight(PanelLightState(is_on=True, brightness_percent=60.0))
        watcher = self.build_watcher(light)

        await self.leave_then_return(watcher, away_minutes=120)

        self.assertEqual(light.asked_for, [])
        self.assertEqual(light.state.brightness_percent, 60.0)
        self.assertEqual(await self.outcomes(), ["light_on"])

    async def test_a_join_with_no_remembered_departure_stays_dark(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)

        await watcher.handle(json.dumps({"mac": MY_PHONE, "event": "joined"}))

        self.assertEqual(light.asked_for, [])
        self.assertEqual(await self.outcomes(), ["no_departure"])

    async def test_an_unreachable_router_keeps_the_light_off(self):
        """Guessing "nobody home" would light an empty hallway; guessing the other way costs one arrival."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)
        watcher.household_calendar.frozen_now -= timedelta(minutes=120)
        await watcher.handle(json.dumps({"mac": MY_PHONE, "event": "left"}))
        watcher.household_calendar.frozen_now += timedelta(minutes=120)
        self.router.reachable = False

        await watcher.handle(json.dumps({"mac": MY_PHONE, "event": "joined"}))

        self.assertEqual(light.asked_for, [])
        self.assertEqual(await self.outcomes(), ["router_silent"])

    async def test_a_phone_recognised_only_by_name_is_met_at_the_door(self):
        """The address iOS wears is not in any configuration — the router calling it an iPhone is the whole proof."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)

        await self.leave_then_return(watcher, away_minutes=120, mac=ROTATED_PHONE)

        self.assertEqual(light.asked_for, [ARRIVAL_PERCENT])
        self.assertEqual(await self.outcomes(), ["raised"])

    async def test_a_laptop_joining_the_wifi_is_neither_recorded_nor_acted_on(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)

        await self.leave_then_return(watcher, away_minutes=120, mac=LAPTOP)

        self.assertEqual(light.asked_for, [])
        self.assertEqual(await self.outcomes(), [])

    async def test_an_address_that_rotated_while_away_arrives_without_a_departure(self):
        """A retired address cannot be matched to the new one, and staying dark is the honest way to be unsure."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)
        watcher.household_calendar.frozen_now -= timedelta(minutes=120)
        await watcher.handle(json.dumps({"mac": MY_PHONE, "event": "left"}))
        watcher.household_calendar.frozen_now += timedelta(minutes=120)

        await watcher.handle(json.dumps({"mac": ROTATED_PHONE, "event": "joined"}))

        self.assertEqual(light.asked_for, [])
        self.assertEqual(await self.outcomes(), ["no_departure"])

    async def test_a_phone_that_is_not_ours_is_neither_recorded_nor_acted_on(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)

        await self.leave_then_return(watcher, away_minutes=120, mac="00:00:5E:00:53:77")

        self.assertEqual(light.asked_for, [])
        self.assertEqual(await self.outcomes(), [])

    async def test_a_message_that_is_not_an_event_is_survived(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)

        await watcher.handle("not json at all")

        self.assertEqual(light.asked_for, [])

    async def test_the_signal_strength_is_kept_with_the_join(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)

        await watcher.handle(json.dumps({"mac": MY_PHONE, "event": "joined", "rssi": -75}))

        async with self.uow as uow:
            events = await uow.presence_events.list_since(datetime(2000, 1, 1, tzinfo=timezone.utc))
        self.assertEqual([event.rssi for event in events], [-75])

    async def test_the_sweep_puts_the_light_out_once_the_welcome_has_expired(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)
        await self.leave_then_return(watcher, away_minutes=120)

        watcher.household_calendar.frozen_now += timedelta(minutes=11)
        await watcher.sweep()

        self.assertEqual(light.asked_for, [ARRIVAL_PERCENT, 0])

    async def test_the_sweep_leaves_the_light_alone_before_the_welcome_expires(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)
        await self.leave_then_return(watcher, away_minutes=120)

        watcher.household_calendar.frozen_now += timedelta(minutes=3)
        await watcher.sweep()

        self.assertEqual(light.asked_for, [ARRIVAL_PERCENT])

    async def test_the_sweep_leaves_a_light_somebody_turned_up_themselves(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)
        await self.leave_then_return(watcher, away_minutes=120)
        light.state = PanelLightState(is_on=True, brightness_percent=80.0)

        watcher.household_calendar.frozen_now += timedelta(minutes=11)
        await watcher.sweep()

        self.assertEqual(light.asked_for, [ARRIVAL_PERCENT])
        self.assertEqual(light.state.brightness_percent, 80.0)

    async def test_two_phones_arriving_together_still_get_the_light(self):
        """Both walk in from an empty flat, so the first must not read the second as somebody already home."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)
        watcher.household_calendar.frozen_now -= timedelta(minutes=120)
        await watcher.handle(json.dumps({"mac": MY_PHONE, "event": "left"}))
        await watcher.handle(json.dumps({"mac": OTHER_PHONE, "event": "left"}))
        watcher.household_calendar.frozen_now += timedelta(minutes=120)
        self.router.online = {MY_PHONE, OTHER_PHONE}

        await watcher.handle(json.dumps({"mac": MY_PHONE, "event": "joined"}))
        await watcher.handle(json.dumps({"mac": OTHER_PHONE, "event": "joined"}))

        self.assertEqual(light.asked_for, [ARRIVAL_PERCENT])
        self.assertEqual(await self.outcomes(), ["raised", "light_on"])

    async def test_a_phone_that_only_hopped_bands_still_counts_as_somebody_home(self):
        """Otherwise a resident's radio flicker would read as arriving beside us and light an occupied flat."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)
        watcher.household_calendar.frozen_now -= timedelta(minutes=120)
        await watcher.handle(json.dumps({"mac": MY_PHONE, "event": "left"}))
        watcher.household_calendar.frozen_now += timedelta(minutes=120) - timedelta(seconds=6)
        await watcher.handle(json.dumps({"mac": OTHER_PHONE, "event": "left"}))
        watcher.household_calendar.frozen_now += timedelta(seconds=6)
        await watcher.handle(json.dumps({"mac": OTHER_PHONE, "event": "joined"}))
        self.router.online = {MY_PHONE, OTHER_PHONE}
        watcher.household_calendar.frozen_now += timedelta(seconds=1)

        await watcher.handle(json.dumps({"mac": MY_PHONE, "event": "joined"}))

        self.assertEqual(light.asked_for, [])
        self.assertEqual(await self.outcomes(), ["hop", "somebody_home"])
