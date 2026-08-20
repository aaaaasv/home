from enum import StrEnum

from src.common.domain import DomainModel


class SystemHealthDimension(StrEnum):
    UNDERVOLTAGE = "undervoltage"
    TEMPERATURE = "temperature"
    DISK = "disk"


class PiHealthReading(DomainModel):
    temperature_celsius: float
    is_undervoltage: bool
    disk_used_percent: float


class SystemHealthIssue(DomainModel):
    dimension: SystemHealthDimension
    value: float | None = None
