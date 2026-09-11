import unittest

from src.bot.handlers.system.formatting import render_media_server_disk_alert
from src.modules.system_health.disk_monitor import DiskHealthMonitor
from src.modules.system_health.domain import DiskFault, DiskReading


def spinning(**overrides) -> DiskReading:
    """The 1 TB drive in the media server, as it actually reads today: worn but with nothing wrong."""
    defaults = dict(
        device="/dev/sda",
        model="ST1000LM035-1RK172",
        healthy=True,
        temperature_celsius=36,
        reallocated_sectors=0,
        pending_sectors=0,
        uncorrectable_sectors=0,
    )
    defaults.update(overrides)
    return DiskReading(**defaults)


def flash(**overrides) -> DiskReading:
    defaults = dict(
        device="/dev/nvme0",
        model="Force MP510",
        healthy=True,
        temperature_celsius=42,
        percentage_used=16,
        available_spare_percent=100,
    )
    defaults.update(overrides)
    return DiskReading(**defaults)


class DiskHealthMonitorTestCase(unittest.TestCase):
    """
    The rarest push in the house: a healthy disk must never trigger it, or nobody will read it when it matters.

    the live media server is the test case that keeps this honest — its 1 TB drive has 116 000 head-load
    cycles and 18 000 power-on hours, and is in perfect health. wear is not a fault.
    """

    def test_evaluate_the_disks_as_they_read_today_says_nothing(self):
        monitor = DiskHealthMonitor()

        issues = monitor.evaluate([spinning(), flash()])

        self.assertEqual(issues, [])

    def test_evaluate_a_first_reallocated_sector_names_the_disk_and_the_count(self):
        monitor = DiskHealthMonitor()

        issues = monitor.evaluate([spinning(reallocated_sectors=8), flash()])

        self.assertEqual(
            [(issue.model, issue.fault, issue.value) for issue in issues],
            [("ST1000LM035-1RK172", DiskFault.REALLOCATED, 8)],
        )

    def test_evaluate_the_same_fault_twice_announces_it_once(self):
        monitor = DiskHealthMonitor()
        monitor.evaluate([spinning(reallocated_sectors=8)])

        issues = monitor.evaluate([spinning(reallocated_sectors=8)])

        self.assertEqual(issues, [])

    def test_evaluate_a_growing_count_stays_quiet_because_the_disk_is_already_condemned(self):
        monitor = DiskHealthMonitor()
        monitor.evaluate([spinning(reallocated_sectors=8)])

        issues = monitor.evaluate([spinning(reallocated_sectors=4096)])

        self.assertEqual(issues, [])

    def test_evaluate_a_second_distinct_fault_on_the_same_disk_is_announced_separately(self):
        monitor = DiskHealthMonitor()
        monitor.evaluate([spinning(reallocated_sectors=8)])

        issues = monitor.evaluate([spinning(reallocated_sectors=8, pending_sectors=2)])

        self.assertEqual([issue.fault for issue in issues], [DiskFault.PENDING])

    def test_evaluate_a_drive_that_condemns_itself_is_announced_before_any_counter(self):
        monitor = DiskHealthMonitor()

        issues = monitor.evaluate([spinning(healthy=False, reallocated_sectors=3)])

        self.assertEqual([issue.fault for issue in issues], [DiskFault.FAILED, DiskFault.REALLOCATED])

    def test_evaluate_flash_below_the_wear_mark_says_nothing(self):
        monitor = DiskHealthMonitor()

        issues = monitor.evaluate([flash(percentage_used=89)])

        self.assertEqual(issues, [])

    def test_evaluate_flash_at_the_wear_mark_is_announced(self):
        monitor = DiskHealthMonitor()

        issues = monitor.evaluate([flash(percentage_used=90)])

        self.assertEqual([(issue.fault, issue.value) for issue in issues], [(DiskFault.WORN, 90)])

    def test_evaluate_flash_eating_into_its_spare_blocks_is_announced(self):
        monitor = DiskHealthMonitor()

        issues = monitor.evaluate([flash(available_spare_percent=20)])

        self.assertEqual([(issue.fault, issue.value) for issue in issues], [(DiskFault.SPARE, 20)])

    def test_evaluate_a_disk_with_no_model_falls_back_to_its_device_name(self):
        monitor = DiskHealthMonitor()

        issues = monitor.evaluate([spinning(model=None, pending_sectors=1)])

        self.assertEqual([issue.model for issue in issues], ["/dev/sda"])


class RenderMediaServerDiskAlertTestCase(unittest.TestCase):
    """Names the disk and the finding, and stops — what to do about a dying drive is not the bot's call."""

    def test_render_one_failing_disk_names_it_and_the_finding(self):
        monitor = DiskHealthMonitor()
        issues = monitor.evaluate([spinning(reallocated_sectors=8)])

        text = render_media_server_disk_alert(issues)

        self.assertEqual(
            text,
            "💽 <b>Медіасервер</b>\n⚠️ ST1000LM035-1RK172 — перерозподілених секторів: 8",
        )

    def test_render_several_findings_puts_each_on_its_own_line(self):
        monitor = DiskHealthMonitor()
        issues = monitor.evaluate([spinning(healthy=False, pending_sectors=2), flash(percentage_used=95)])

        text = render_media_server_disk_alert(issues)

        self.assertEqual(
            text,
            "💽 <b>Медіасервер</b>\n"
            "❌ ST1000LM035-1RK172 — SMART каже, що диск помирає\n"
            "⚠️ ST1000LM035-1RK172 — секторів в очікуванні: 2\n"
            "⌛ Force MP510 — витрачено 95% ресурсу",
        )
