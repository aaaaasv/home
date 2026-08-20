import unittest

from src.modules.system_health.domain import PiHealthReading, SystemHealthDimension
from src.modules.system_health.monitor import SystemHealthMonitor


def build_monitor() -> SystemHealthMonitor:
    return SystemHealthMonitor(
        temperature_alert_celsius=75.0,
        temperature_recovery_celsius=68.0,
        disk_alert_percent=90.0,
        disk_recovery_percent=85.0,
    )


def build_reading(
    temperature_celsius: float = 55.0, is_undervoltage: bool = False, disk_used_percent: float = 35.0
) -> PiHealthReading:
    return PiHealthReading(
        temperature_celsius=temperature_celsius,
        is_undervoltage=is_undervoltage,
        disk_used_percent=disk_used_percent,
    )


class SystemHealthMonitorTestCase(unittest.TestCase):
    def test_evaluate_a_healthy_reading_reports_nothing(self):
        monitor = build_monitor()

        issues = monitor.evaluate(build_reading())

        self.assertEqual(issues, [])

    def test_evaluate_a_hot_pi_reports_the_temperature_once(self):
        monitor = build_monitor()

        first = monitor.evaluate(build_reading(temperature_celsius=78.0))
        second = monitor.evaluate(build_reading(temperature_celsius=79.0))

        self.assertEqual([issue.dimension for issue in first], [SystemHealthDimension.TEMPERATURE])
        self.assertEqual(first[0].value, 78.0)
        self.assertEqual(second, [])

    def test_evaluate_stays_quiet_while_the_temperature_hovers_above_the_recovery_threshold(self):
        monitor = build_monitor()
        monitor.evaluate(build_reading(temperature_celsius=78.0))

        hovering = monitor.evaluate(build_reading(temperature_celsius=72.0))

        self.assertEqual(hovering, [])

    def test_evaluate_reports_again_after_the_temperature_recovers_and_relapses(self):
        monitor = build_monitor()
        monitor.evaluate(build_reading(temperature_celsius=78.0))
        monitor.evaluate(build_reading(temperature_celsius=67.0))

        relapse = monitor.evaluate(build_reading(temperature_celsius=78.0))

        self.assertEqual([issue.dimension for issue in relapse], [SystemHealthDimension.TEMPERATURE])

    def test_evaluate_reports_undervoltage(self):
        monitor = build_monitor()

        issues = monitor.evaluate(build_reading(is_undervoltage=True))

        self.assertEqual([issue.dimension for issue in issues], [SystemHealthDimension.UNDERVOLTAGE])

    def test_evaluate_reports_a_full_disk_with_its_percentage(self):
        monitor = build_monitor()

        issues = monitor.evaluate(build_reading(disk_used_percent=92.0))

        self.assertEqual([issue.dimension for issue in issues], [SystemHealthDimension.DISK])
        self.assertEqual(issues[0].value, 92.0)

    def test_evaluate_reports_several_problems_together_in_order(self):
        monitor = build_monitor()

        issues = monitor.evaluate(build_reading(temperature_celsius=80.0, is_undervoltage=True, disk_used_percent=95.0))

        self.assertEqual(
            [issue.dimension for issue in issues],
            [SystemHealthDimension.UNDERVOLTAGE, SystemHealthDimension.TEMPERATURE, SystemHealthDimension.DISK],
        )
