from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum

from src.common.domain import DomainModel


class GridState(StrEnum):
    """What the station's numbers say about the wall socket — UNKNOWN when they cannot say."""

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
