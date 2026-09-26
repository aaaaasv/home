import json
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.bot.handlers.presence.arrival import ArrivalLightWatcher
from src.common.config import Settings
from src.modules.lighting.domain import PanelLightState
from src.tests.fakes import FrozenHouseholdCalendar

KYIV = ZoneInfo("Europe/Kyiv")
# 22:00 in Kyiv in late September — the sun is eleven degrees down, which is properly dark
NIGHT = datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc)
# and 13:00 local on the same day, which is not
DAY = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)

MY_PHONE = "AA:BB:CC:DD:EE:01"
OTHER_PHONE = "AA:BB:CC:DD:EE:02"
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


class ScriptedPresence:
    def __init__(self, online):
        self.online = online

    async def online_macs(self):
        return self.online


class ArrivalLightTestCase(unittest.IsolatedAsyncioTestCase):
    """
    Meeting somebody at the door — and, more to the point, the four cases where it refuses to.

    the refusals are the reason this can stay switched on: the router's own log shows a phone leaving and
    rejoining inside six seconds, so a rule that simply answered «з'явився» would blink all day.
    """

    def build_watcher(self, light, online=frozenset(), now=NIGHT) -> ArrivalLightWatcher:
        return ArrivalLightWatcher(
            panel_light=light,
            presence_source=ScriptedPresence(online),
            settings=Settings(
                TELEGRAM_BOT_TOKEN="123:abc",
                PRESENCE_PHONE_MACS=f"{MY_PHONE},{OTHER_PHONE}",
                PRESENCE_LATITUDE=50.45,
                PRESENCE_LONGITUDE=30.52,
                ARRIVAL_LIGHT_PERCENT=ARRIVAL_PERCENT,
                ARRIVAL_AWAY_MINUTES=AWAY_MINUTES,
                ARRIVAL_LIGHT_MINUTES=10,
            ),
            household_calendar=FrozenHouseholdCalendar(timezone=KYIV, frozen_now=now),
        )

    async def leave_then_return(self, watcher, away_minutes: int, mac: str = MY_PHONE) -> None:
        watcher.household_calendar.frozen_now -= timedelta(minutes=away_minutes)
        await watcher.handle(json.dumps({"mac": mac, "event": "left"}))
        watcher.household_calendar.frozen_now += timedelta(minutes=away_minutes)
        await watcher.handle(json.dumps({"mac": mac, "event": "joined"}))

    async def test_coming_home_after_a_real_absence_in_the_dark_raises_the_light(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)

        await self.leave_then_return(watcher, away_minutes=120)

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

    async def test_coming_home_in_daylight_leaves_the_light_off(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light, now=DAY)

        await self.leave_then_return(watcher, away_minutes=120)

        self.assertEqual(light.asked_for, [])

    async def test_coming_home_to_a_flat_that_is_not_empty_leaves_the_light_off(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light, online={OTHER_PHONE})

        await self.leave_then_return(watcher, away_minutes=120)

        self.assertEqual(light.asked_for, [])

    async def test_coming_home_to_a_light_already_on_leaves_it_where_it_was(self):
        light = RecordingPanelLight(PanelLightState(is_on=True, brightness_percent=60.0))
        watcher = self.build_watcher(light)

        await self.leave_then_return(watcher, away_minutes=120)

        self.assertEqual(light.asked_for, [])
        self.assertEqual(light.state.brightness_percent, 60.0)

    async def test_a_phone_that_is_not_ours_is_ignored(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)

        await self.leave_then_return(watcher, away_minutes=120, mac="11:22:33:44:55:66")

        self.assertEqual(light.asked_for, [])

    async def test_a_join_with_no_remembered_departure_stays_dark(self):
        """After a restart there is no absence to measure, and being unsure should look like doing nothing."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)

        await watcher.handle(json.dumps({"mac": MY_PHONE, "event": "joined"}))

        self.assertEqual(light.asked_for, [])

    async def test_an_unreachable_router_keeps_the_light_off(self):
        """Guessing "nobody home" would light an empty hallway; guessing the other way costs one arrival."""
        light = RecordingPanelLight()
        watcher = self.build_watcher(light, online=None)

        await self.leave_then_return(watcher, away_minutes=120)

        self.assertEqual(light.asked_for, [])

    async def test_a_message_that_is_not_an_event_is_survived(self):
        light = RecordingPanelLight()
        watcher = self.build_watcher(light)

        await watcher.handle("not json at all")

        self.assertEqual(light.asked_for, [])

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
