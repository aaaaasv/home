from src.modules.system_health.domain import DiskFault, DiskIssue, DiskReading

# a flash drive that has consumed this much of its rated endurance, or has eaten this far into its spare
# blocks, is on notice — neither is an emergency, but both mean the replacement should be bought, not planned
WORN_PERCENT = 90
SPARE_PERCENT = 20


class DiskHealthMonitor:
    """
    Turns disk readings into alerts that fire once and then stay quiet.

    deliberately without the hysteresis its sibling `SystemHealthMonitor` has, because these faults do not
    recover: a reallocated sector never un-reallocates, and consumed flash endurance never comes back. so the
    rule is simply once per disk per fault, for as long as this process lives.

    the state is in memory on purpose. a restart re-announcing a failing disk is not noise — it is a disk that
    is still failing, and the message is rare enough that saying it twice costs nothing.
    """

    def __init__(self, worn_percent: int = WORN_PERCENT, spare_percent: int = SPARE_PERCENT):
        self.worn_percent = worn_percent
        self.spare_percent = spare_percent
        self._announced: set[tuple[str, DiskFault]] = set()

    def evaluate(self, readings: list[DiskReading]) -> list[DiskIssue]:
        fresh = [issue for reading in readings for issue in self._faults(reading)]
        unannounced = [issue for issue in fresh if (issue.model, issue.fault) not in self._announced]
        for issue in unannounced:
            self._announced.add((issue.model, issue.fault))
        return unannounced

    def _faults(self, reading: DiskReading) -> list[DiskIssue]:
        model = reading.model or reading.device
        issues: list[DiskIssue] = []

        # `healthy` is the drive's own verdict on itself, and it is the only one that means "replace it today"
        if reading.healthy is False:
            issues.append(DiskIssue(model=model, fault=DiskFault.FAILED))

        for fault, count in (
            (DiskFault.REALLOCATED, reading.reallocated_sectors),
            (DiskFault.PENDING, reading.pending_sectors),
            (DiskFault.UNCORRECTABLE, reading.uncorrectable_sectors),
        ):
            if count:
                issues.append(DiskIssue(model=model, fault=fault, value=count))

        if reading.percentage_used is not None and reading.percentage_used >= self.worn_percent:
            issues.append(DiskIssue(model=model, fault=DiskFault.WORN, value=reading.percentage_used))
        if reading.available_spare_percent is not None and reading.available_spare_percent <= self.spare_percent:
            issues.append(DiskIssue(model=model, fault=DiskFault.SPARE, value=reading.available_spare_percent))
        return issues
