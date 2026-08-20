from enum import StrEnum

from src.common.domain import DomainModel


class AirConditionerMode(StrEnum):
    AUTO = "auto"
    COOL = "cool"
    DRY = "dry"
    FAN = "fan"
    HEAT = "heat"


class AirConditionerFanSpeed(StrEnum):
    # the unit offers six steps, but a phone button cycles a legible four; the gree layer maps between them
    AUTO = "auto"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AirConditionerState(DomainModel):
    is_on: bool
    mode: AirConditionerMode
    target_temperature_celsius: int
    # the unit's own sensor, mounted high on the wall — trust the room sensor over it for anything precise
    room_temperature_celsius: int | None
    fan_speed: AirConditionerFanSpeed = AirConditionerFanSpeed.AUTO
    # turbo forces maximum airflow and quiet the minimum, so the unit treats them as mutually exclusive
    turbo: bool = False
    quiet: bool = False
    # blows the coil dry after cooling stops, to keep mildew and its smell out of the split
    xfan: bool = False


class AirConditionerRuntimeNotice(DomainModel):
    hours: int
    room_temperature_celsius: int | None
