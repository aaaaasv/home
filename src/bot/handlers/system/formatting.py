"""How the Pi health alert and status card render."""
from src.bot.handlers.system.messages import (
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
from src.modules.system_health.domain import PiHealthReading, SystemHealthDimension, SystemHealthIssue


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
