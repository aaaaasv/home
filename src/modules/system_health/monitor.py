from src.modules.system_health.domain import PiHealthReading, SystemHealthDimension, SystemHealthIssue


class SystemHealthMonitor:
    """
    Turns a stream of pi readings into alerts that fire once per episode.

    it stays silent while a problem persists and speaks again only after the reading clearly recovers, so a value
    that hovers around its threshold cannot flap the tech topic. the state lives in memory: a restart re-surfacing
    an active problem is fine — it is a real problem — and it keeps this off the database.
    """

    def __init__(
        self,
        temperature_alert_celsius: float,
        temperature_recovery_celsius: float,
        disk_alert_percent: float,
        disk_recovery_percent: float,
    ):
        self.temperature_alert_celsius = temperature_alert_celsius
        self.temperature_recovery_celsius = temperature_recovery_celsius
        self.disk_alert_percent = disk_alert_percent
        self.disk_recovery_percent = disk_recovery_percent
        self._alerted: set[SystemHealthDimension] = set()

    def evaluate(self, reading: PiHealthReading) -> list[SystemHealthIssue]:
        for dimension in list(self._alerted):
            if self._has_recovered(dimension, reading):
                self._alerted.discard(dimension)

        fresh_issues = [issue for issue in self._current_issues(reading) if issue.dimension not in self._alerted]
        for issue in fresh_issues:
            self._alerted.add(issue.dimension)
        return fresh_issues

    def _current_issues(self, reading: PiHealthReading) -> list[SystemHealthIssue]:
        issues: list[SystemHealthIssue] = []
        if reading.is_undervoltage:
            issues.append(SystemHealthIssue(dimension=SystemHealthDimension.UNDERVOLTAGE))
        if reading.temperature_celsius >= self.temperature_alert_celsius:
            issues.append(
                SystemHealthIssue(dimension=SystemHealthDimension.TEMPERATURE, value=reading.temperature_celsius)
            )
        if reading.disk_used_percent >= self.disk_alert_percent:
            issues.append(SystemHealthIssue(dimension=SystemHealthDimension.DISK, value=reading.disk_used_percent))
        return issues

    def _has_recovered(self, dimension: SystemHealthDimension, reading: PiHealthReading) -> bool:
        if dimension == SystemHealthDimension.UNDERVOLTAGE:
            return not reading.is_undervoltage
        if dimension == SystemHealthDimension.TEMPERATURE:
            return reading.temperature_celsius < self.temperature_recovery_celsius
        if dimension == SystemHealthDimension.DISK:
            return reading.disk_used_percent < self.disk_recovery_percent
        return True
