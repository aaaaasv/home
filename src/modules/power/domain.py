from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from src.common.domain import DomainModel


class GridState(StrEnum):
    """Whether the city grid is up — UNKNOWN when neither the hat nor the station can say."""

    ON_GRID = "on_grid"
    ON_BATTERY = "on_battery"
    UNKNOWN = "unknown"


class EcoFlowState(DomainModel):
    """A Delta 2 snapshot read over local ble — as_of stamps when, since it may be a cached reading"""

    battery_percent: float
    # ac input watts above zero means the station is charging from the wall — the interim "mains present" signal
    on_mains: bool
    ac_input_power: int
    ac_output_power: int
    ac_output_on: bool
    usb_output_on: bool
    dc_output_on: bool
    # minutes to full while on mains, minutes of runtime left while on battery — None until the station reports it
    remaining_minutes: int | None
    charge_limit_max: int | None
    backup_reserve_percent: int | None
    cell_temperature_celsius: int | None
    as_of: datetime


class UpsState(DomainModel):
    """
    What the pi's own hat reports — the only direct measurement of the wall socket anywhere in the flat.

    the station has to infer mains from watts and gets it wrong on an idle full battery; this pin is wired to
    the socket itself, so it answers even when the station is shelved, unreachable or not owned at all.
    """

    # the x728 holds this line low while the socket feeds it and lets the pull-up take it high on loss
    mains_present: bool
    battery_volts: float
    # the gauge re-learns the pack after a cell swap and reads nonsense meanwhile — 4% at 3.78 V on 08.09,
    # which was really ~45%. compare voltages, never this, when the answer has to be right
    battery_percent: float
    as_of: datetime


class MediaServerState(DomainModel):
    """
    What the media server's own battery says about itself, as its agent publishes it.

    `charge_percent` is reported and shown, but it is never what the runtime is computed from. the pack is
    capped at 60% by `battery-charge-limit.service` and under a standing cap `energy_full` never gets the full
    cycle it would need to recalibrate — the kernel reads 64% against it while the cap is 60. energy over
    watts is a direct measurement with no such denominator in it.
    """

    on_mains: bool
    is_charging: bool
    charge_percent: float
    energy_watt_hours: float
    power_watts: float
    as_of: datetime


class ReserveLayer(StrEnum):
    """The four things that have to outlive a blackout, in the order the board lists them."""

    STATION = "station"
    PI = "pi"
    ROUTER = "router"
    MEDIA_SERVER = "media_server"


class ReserveStanding(StrEnum):
    """
    How one layer is doing, in terms that survive four different kinds of sensor.

    the station reports minutes, the hat reports volts, the router reports nothing at all — so the board says
    what they have in common and stays silent about the rest. HOLDING_UNMEASURED is the honest answer where
    nothing measures the runtime yet: alive, and for how long it has been, but no promise about the end.
    """

    HOLDING = "holding"
    HOLDING_UNMEASURED = "holding_unmeasured"
    CHARGING = "charging"
    FULL = "full"
    ALIVE = "alive"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class ReserveRow:
    """One layer as the board shows it: how it stands, and how long that lasts where anything can say."""

    layer: ReserveLayer
    standing: ReserveStanding
    # what the layer says about its own charge — the router has no way to say anything at all
    charge_percent: int | None = None
    # time left on battery, or time to full while charging — only where something measures it
    remaining: timedelta | None = None
    # how long it has been running on its own battery, for the layers where that is all anyone can say
    holding_for: timedelta | None = None


@dataclass(frozen=True)
class Reserve:
    """
    Every backup layer on one screen, under one shared answer to "are we on the city grid or not".

    that answer is a single fact, not four — the hat is wired to the socket and speaks for the whole flat —
    so it belongs in the heading and leaves the rows free to be about time alone.
    """

    grid: GridState
    rows: tuple[ReserveRow, ...]
    # how long the flat has been on battery, counted from the first reading that saw it — None on the grid, and
    # None through an outage the bot woke up inside, where the honest answer is that nobody watched the start
    on_battery_for: timedelta | None = None


MINUTES_PER_DAY = 24 * 60


class OutageScheduleStatus(StrEnum):
    NO_OUTAGES = "NoOutages"
    SCHEDULE_APPLIES = "ScheduleApplies"
    WAITING_FOR_SCHEDULE = "WaitingForSchedule"
    EMERGENCY_SHUTDOWNS = "EmergencyShutdowns"
    UNKNOWN = "Unknown"

    @classmethod
    def _missing_(cls, value: object) -> "OutageScheduleStatus":
        # an unfamiliar status must not crash the poll — treat it as unknown and let the caller stay quiet
        return cls.UNKNOWN


@dataclass(frozen=True)
class OutageInterval:
    """One definite off-period, held as minutes from midnight so an end at 24:00 has an exact representation"""

    start_minute: int
    end_minute: int

    @property
    def start(self) -> time:
        return _minutes_to_time(self.start_minute)

    @property
    def end(self) -> time:
        # 1440 is midnight-end-of-day, which `time` cannot hold; render it as 23:59 so it stays within the day
        return _minutes_to_time(min(self.end_minute, MINUTES_PER_DAY - 1))

    def contains_minute(self, minute_of_day: int) -> bool:
        return self.start_minute <= minute_of_day < self.end_minute


@dataclass(frozen=True)
class OutageSchedule:
    """The outage picture for one group on one calendar day"""

    day: date
    status: OutageScheduleStatus
    off_intervals: tuple[OutageInterval, ...]
    updated_on: datetime | None

    @property
    def has_outages(self) -> bool:
        return bool(self.off_intervals)

    def is_off_at(self, moment: datetime) -> bool:
        """Whether the group is scheduled off at the given local wall-clock moment (meaningful for moment on day)"""
        return any(interval.contains_minute(_minute_of_day(moment)) for interval in self.off_intervals)

    def current_off_interval(self, moment: datetime) -> OutageInterval | None:
        """The off-period this local moment falls inside — the one whose end is when the light comes back."""
        minute_of_day = _minute_of_day(moment)
        for interval in self.off_intervals:
            if interval.contains_minute(minute_of_day):
                return interval
        return None

    def next_off_interval(self, moment: datetime) -> OutageInterval | None:
        """The first off-period that starts strictly after the given local moment — feeds the pre-outage ping"""
        minute_of_day = _minute_of_day(moment)
        for interval in self.off_intervals:
            if interval.start_minute > minute_of_day:
                return interval
        return None


@dataclass(frozen=True)
class OutageOutlook:
    """Today and tomorrow together, parsed from a single fetch"""

    today: OutageSchedule
    tomorrow: OutageSchedule | None


def _minutes_to_time(minutes: int) -> time:
    return time(hour=minutes // 60, minute=minutes % 60)


def _minute_of_day(moment: datetime) -> int:
    return moment.hour * 60 + moment.minute


@dataclass(frozen=True)
class OutageForecast:
    """How the station's remaining runtime compares with the hour the schedule promises the light back."""

    runs_out_at: datetime
    power_returns_at: datetime

    @property
    def shortfall(self) -> timedelta:
        """How long the family would sit in the dark — zero or less when the battery reaches."""
        return self.power_returns_at - self.runs_out_at

    @property
    def reaches(self) -> bool:
        return self.shortfall <= timedelta(0)
