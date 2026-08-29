import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.bot.handlers.power.formatting import render_outage_forecast
from src.bot.handlers.power.jobs import OutageForecastJob
from src.modules.power.domain import EcoFlowState, OutageInterval, OutageSchedule, OutageScheduleStatus
from src.modules.power.outage_forecast import forecast_outage
from src.tests.fakes import FrozenHouseholdCalendar, RecordingBot, StubForumTopic

KYIV = ZoneInfo("Europe/Kyiv")
TODAY = date(2026, 12, 4)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(TODAY.year, TODAY.month, TODAY.day, hour, minute, tzinfo=KYIV)


def build_state(**overrides) -> EcoFlowState:
    defaults = dict(
        battery_percent=64.0,
        on_mains=False,
        ac_input_power=0,
        ac_output_power=180,
        ac_output_on=True,
        usb_output_on=False,
        dc_output_on=False,
        remaining_minutes=100,
        charge_limit_max=80,
        backup_reserve_percent=None,
        cell_temperature_celsius=9,
        as_of=at(13, 0),
    )
    defaults.update(overrides)
    return EcoFlowState(**defaults)


def on_grid(**overrides) -> EcoFlowState:
    return build_state(on_mains=True, ac_input_power=300, **overrides)


def build_schedule(*intervals: tuple[int, int], day: date = TODAY) -> OutageSchedule:
    return OutageSchedule(
        day=day,
        status=OutageScheduleStatus.SCHEDULE_APPLIES,
        off_intervals=tuple(OutageInterval(start * 60, end * 60) for start, end in intervals),
        updated_on=None,
    )


class ForecastOutageTestCase(unittest.TestCase):
    """
    Whether the station reaches the hour the schedule promises the light back.

    the station's own runtime estimate is trusted rather than a consumption model of ours: it already knows
    what the flat is drawing, which is the hard half. everything else here is about refusing to answer when
    the question cannot honestly be answered.
    """

    def test_a_battery_that_runs_out_before_the_light_returns_reports_the_gap(self):
        # 13:00, 100 minutes left, the light is scheduled back at 16:00
        forecast = forecast_outage(build_state(remaining_minutes=100), build_schedule((12, 16)), at(13, 0))

        self.assertEqual((forecast.runs_out_at, forecast.power_returns_at), (at(14, 40), at(16, 0)))
        self.assertEqual((forecast.reaches, forecast.shortfall), (False, timedelta(hours=1, minutes=20)))

    def test_a_battery_that_lasts_past_the_return_reports_that_it_reaches(self):
        forecast = forecast_outage(build_state(remaining_minutes=300), build_schedule((12, 16)), at(13, 0))

        self.assertTrue(forecast.reaches)

    def test_a_station_on_mains_is_not_forecast_at_all(self):
        forecast = forecast_outage(on_grid(), build_schedule((12, 16)), at(13, 0))

        self.assertIsNone(forecast)

    def test_an_unreachable_station_is_not_forecast(self):
        forecast = forecast_outage(None, build_schedule((12, 16)), at(13, 0))

        self.assertIsNone(forecast)

    def test_a_station_that_reports_no_runtime_estimate_is_not_forecast(self):
        forecast = forecast_outage(build_state(remaining_minutes=None), build_schedule((12, 16)), at(13, 0))

        self.assertIsNone(forecast)

    def test_a_blackout_outside_the_published_schedule_is_not_forecast(self):
        """An emergency shutdown has no promised end, and inventing one is worse than saying nothing."""
        forecast = forecast_outage(build_state(), build_schedule((18, 20)), at(13, 0))

        self.assertIsNone(forecast)

    def test_yesterdays_schedule_is_not_used_for_todays_outage(self):
        stale = build_schedule((12, 16), day=date(2026, 12, 3))

        forecast = forecast_outage(build_state(), stale, at(13, 0))

        self.assertIsNone(forecast)

    def test_the_return_is_read_from_the_interval_the_outage_is_actually_in(self):
        # two outages today; the one running at 13:00 ends at 16:00, not the later one at 20:00
        forecast = forecast_outage(build_state(), build_schedule((12, 16), (18, 20)), at(13, 0))

        self.assertEqual(forecast.power_returns_at, at(16, 0))


class RenderOutageForecastTestCase(unittest.TestCase):
    def test_the_warning_names_both_hours_and_the_gap_between_them(self):
        forecast = forecast_outage(build_state(remaining_minutes=100), build_schedule((12, 16)), at(13, 0))

        text = render_outage_forecast(forecast)

        self.assertEqual(
            text,
            "🪫 <b>Не дотягне до світла</b>\n\n"
            "Батарея сяде о 14:40, а світло за графіком о 16:00.\n"
            "Бракує 1 год 20 хв — варто зняти зайве навантаження.",
        )


class StubEcoFlowStation:
    def __init__(self, states: list[EcoFlowState | None]):
        self.states = list(states)

    async def read_state(self, refresh: bool = False) -> EcoFlowState | None:
        return self.states.pop(0) if self.states else None


class StubScheduleProvider:
    def __init__(self, schedule: OutageSchedule | None):
        self.schedule = schedule
        self.fetches = 0

    async def fetch_today(self) -> OutageSchedule | None:
        self.fetches += 1
        return self.schedule


def build_job(states, schedule, bot=None) -> OutageForecastJob:
    return OutageForecastJob(
        bot=bot or RecordingBot(),
        chat_id=-100,
        power_topic=StubForumTopic(),
        ecoflow_station=StubEcoFlowStation(states),
        schedule_provider=StubScheduleProvider(schedule),
        household_calendar=FrozenHouseholdCalendar(KYIV, frozen_now=at(13, 0)),
    )


class OutageForecastJobTestCase(unittest.IsolatedAsyncioTestCase):
    """
    The push that must normally be empty.

    a warning repeated every five minutes through a four-hour outage is how a family mutes the topic — and a
    muted topic takes the plant digest down with it.
    """

    async def test_a_shortfall_is_announced_once_however_long_the_outage_lasts(self):
        bot = RecordingBot()
        short = build_state(remaining_minutes=100)
        job = build_job([short, short, short], build_schedule((12, 16)), bot=bot)

        for _ in range(3):
            await job()

        self.assertEqual(len(bot.sent), 1)

    async def test_a_battery_that_reaches_says_nothing_at_all(self):
        bot = RecordingBot()
        job = build_job([build_state(remaining_minutes=300)], build_schedule((12, 16)), bot=bot)

        await job()

        self.assertEqual(bot.sent, [])

    async def test_the_warning_pings_because_it_carries_a_deadline(self):
        bot = RecordingBot()
        job = build_job([build_state(remaining_minutes=100)], build_schedule((12, 16)), bot=bot)

        await job()

        self.assertEqual(bot.sent[0]["silent"], False)

    async def test_a_new_outage_after_the_light_returns_is_warned_about_again(self):
        bot = RecordingBot()
        short = build_state(remaining_minutes=100)
        job = build_job([short, on_grid(), short], build_schedule((12, 16)), bot=bot)

        for _ in range(3):
            await job()

        self.assertEqual(len(bot.sent), 2)

    async def test_the_last_known_schedule_is_used_when_the_fetch_fails_mid_outage(self):
        """The hour this question matters is the hour the internet may be gone too."""
        bot = RecordingBot()
        short = build_state(remaining_minutes=100)
        job = build_job([short, short], build_schedule((12, 16)), bot=bot)
        await job()
        job.schedule_provider.schedule = None
        job._warned = False

        await job()

        self.assertEqual(len(bot.sent), 2)
