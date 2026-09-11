"""How the Pi health alert, the status card and the media server disk alert render."""
from src.bot.handlers.system.messages import (
    MEDIA_SERVER_DISK_FAILED,
    MEDIA_SERVER_DISK_PENDING,
    MEDIA_SERVER_DISK_REALLOCATED,
    MEDIA_SERVER_DISK_SPARE,
    MEDIA_SERVER_DISK_TITLE,
    MEDIA_SERVER_DISK_UNCORRECTABLE,
    MEDIA_SERVER_DISK_WORN,
    PI_STATUS_DISK,
    PI_STATUS_POWER_LOW,
    PI_STATUS_POWER_OK,
    PI_STATUS_TEMPERATURE,
    PI_STATUS_TITLE,
    SYSTEM_HEALTH_ALERT_TITLE,
    SYSTEM_HEALTH_DISK,
    SYSTEM_HEALTH_TEMPERATURE,
    SYSTEM_HEALTH_UNDERVOLTAGE,
)
from src.modules.system_health.domain import (
    DiskFault,
    DiskIssue,
    PiHealthReading,
    SystemHealthDimension,
    SystemHealthIssue,
)


def render_system_health_alert(issues: list[SystemHealthIssue]) -> str:
    lines = [SYSTEM_HEALTH_ALERT_TITLE]
    for issue in issues:
        if issue.dimension == SystemHealthDimension.UNDERVOLTAGE:
            lines.append(SYSTEM_HEALTH_UNDERVOLTAGE)
        elif issue.dimension == SystemHealthDimension.TEMPERATURE:
            lines.append(SYSTEM_HEALTH_TEMPERATURE.format(temperature=f"{issue.value:.0f}"))
        elif issue.dimension == SystemHealthDimension.DISK:
            lines.append(SYSTEM_HEALTH_DISK.format(percent=f"{issue.value:.0f}"))
    return "\n".join(lines)


def render_pi_health(reading: PiHealthReading) -> str:
    return "\n".join(
        [
            PI_STATUS_TITLE,
            PI_STATUS_TEMPERATURE.format(temperature=f"{reading.temperature_celsius:.0f}"),
            PI_STATUS_POWER_LOW if reading.is_undervoltage else PI_STATUS_POWER_OK,
            PI_STATUS_DISK.format(percent=f"{reading.disk_used_percent:.0f}"),
        ]
    )


DISK_FAULT_LINES = {
    DiskFault.FAILED: MEDIA_SERVER_DISK_FAILED,
    DiskFault.REALLOCATED: MEDIA_SERVER_DISK_REALLOCATED,
    DiskFault.PENDING: MEDIA_SERVER_DISK_PENDING,
    DiskFault.UNCORRECTABLE: MEDIA_SERVER_DISK_UNCORRECTABLE,
    DiskFault.WORN: MEDIA_SERVER_DISK_WORN,
    DiskFault.SPARE: MEDIA_SERVER_DISK_SPARE,
}


def render_media_server_disk_alert(issues: list[DiskIssue]) -> str:
    """Names the disk and the finding, and stops there — what to do about a dying drive is not the bot's call."""
    lines = [MEDIA_SERVER_DISK_TITLE]
    lines.extend(DISK_FAULT_LINES[issue.fault].format(model=issue.model, value=issue.value) for issue in issues)
    return "\n".join(lines)
