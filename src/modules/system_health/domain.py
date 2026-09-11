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


class DiskFault(StrEnum):
    """
    The handful of SMART facts that actually predict a dying disk, as opposed to merely describing a worn one.

    head-load cycles and power-on hours are deliberately absent. the media server's 1 TB drive has 116 000 of
    the former and is perfectly healthy — reporting that as a fault would teach the family to ignore this
    alert, which is the one failure mode that matters for a message that should fire once a decade.
    """

    FAILED = "failed"
    REALLOCATED = "reallocated"
    PENDING = "pending"
    UNCORRECTABLE = "uncorrectable"
    WORN = "worn"
    SPARE = "spare"


class DiskReading(DomainModel):
    """One disk as its host reports it — the spinning and the solid-state kinds share only the first fields"""

    device: str
    model: str | None
    healthy: bool | None
    temperature_celsius: int | None = None
    reallocated_sectors: int | None = None
    pending_sectors: int | None = None
    uncorrectable_sectors: int | None = None
    percentage_used: int | None = None
    available_spare_percent: int | None = None


class DiskIssue(DomainModel):
    model: str
    fault: DiskFault
    value: int | None = None
