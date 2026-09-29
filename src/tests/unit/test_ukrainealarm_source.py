import unittest

from src.infrastructure.adapters.ukrainealarm_source import UkraineAlarmSource, read_region_alert
from src.modules.air_alert.domain import AirAlert, AlertLevel

# exactly as the feed answered on 25.09.2026 during a real alert, kept whole so a changed shape fails here
KYIV_YELLOW = {
    "regionId": "31",
    "regionType": "State",
    "regionName": "м. Київ",
    "regionEngName": "Kyiv",
    "lastUpdate": "2026-09-25T08:58:05.829282Z",
    "activeAlerts": [
        {
            "regionId": "31",
            "regionType": "State",
            "type": "AIR",
            "lastUpdate": "2026-09-25T08:57:49.824902Z",
            "activeAlertLevels": [
                {
                    "alertLevel": "Yellow",
                    "reason": "Дронова загроза (жовтий рівень)",
                    "createdAt": "2026-09-25T08:57:50.062515Z",
                }
            ],
        }
    ],
}

KYIV_OBLAST_RED = {
    "regionName": "Київська область",
    "activeAlerts": [{"type": "AIR", "activeAlertLevels": [{"alertLevel": "Red", "reason": "Ракетна загроза"}]}],
}


class ReadRegionAlertTestCase(unittest.TestCase):
    """
    Reading one city out of the whole country's alert list.

    the city and the oblast around it are separate records, and that separation is the feature: an oblast
    alert with a calm city must never turn a light on in the city.
    """

    def test_read_region_alert_takes_the_level_and_the_reason(self):
        alert = read_region_alert([KYIV_YELLOW], "м. Київ")

        self.assertEqual(alert.level, AlertLevel.YELLOW)
        self.assertEqual(alert.reason, "Дронова загроза (жовтий рівень)")

    def test_read_region_alert_reads_red_as_red(self):
        red = {**KYIV_YELLOW}
        red["activeAlerts"] = [{"type": "AIR", "activeAlertLevels": [{"alertLevel": "Red", "reason": "Ракета"}]}]

        alert = read_region_alert([red], "м. Київ")

        self.assertEqual(alert.level, AlertLevel.RED)

    def test_read_region_alert_for_a_region_not_in_the_list_is_the_all_clear(self):
        alert = read_region_alert([KYIV_OBLAST_RED], "м. Київ")

        self.assertEqual(alert.level, AlertLevel.NONE)
        self.assertEqual(alert.reason, None)

    def test_read_region_alert_ignores_an_alert_that_is_not_an_air_one(self):
        artillery = {
            "regionName": "м. Київ",
            "activeAlerts": [{"type": "ARTILLERY", "activeAlertLevels": [{"alertLevel": "Red"}]}],
        }

        alert = read_region_alert([artillery], "м. Київ")

        self.assertEqual(alert.level, AlertLevel.NONE)

    def test_read_region_alert_with_an_empty_list_is_the_all_clear(self):
        self.assertEqual(read_region_alert([], "м. Київ").level, AlertLevel.NONE)

    def test_read_region_alert_survives_a_record_that_is_not_a_region(self):
        self.assertEqual(read_region_alert(["nonsense", None, KYIV_YELLOW], "м. Київ").level, AlertLevel.YELLOW)

    def test_read_region_alert_with_a_level_it_has_never_heard_of_is_the_all_clear(self):
        purple = {
            "regionName": "м. Київ",
            "activeAlerts": [{"type": "AIR", "activeAlertLevels": [{"alertLevel": "Purple"}]}],
        }

        self.assertEqual(read_region_alert([purple], "м. Київ").level, AlertLevel.NONE)


class SeverityTestCase(unittest.TestCase):
    """
    A region can carry several levels at once, and the order they arrive in is not a fact about the sky.

    reading the first entry made the level flip with the ordering: on the night of 29.09 the welcome light
    came up a second time at 02:12 on a «new» red that nobody on the ground had seen.
    """

    def build_kyiv(self, *levels) -> dict:
        return {
            "regionName": "м. Київ",
            "activeAlerts": [
                {
                    "type": "AIR",
                    "activeAlertLevels": [{"alertLevel": level, "reason": f"{level} рівень"} for level in levels],
                }
            ],
        }

    def test_read_region_alert_takes_red_when_it_is_listed_after_yellow(self):
        alert = read_region_alert([self.build_kyiv("Yellow", "Red")], "м. Київ")

        self.assertEqual(alert.level, AlertLevel.RED)

    def test_read_region_alert_takes_red_when_it_is_listed_before_yellow(self):
        alert = read_region_alert([self.build_kyiv("Red", "Yellow")], "м. Київ")

        self.assertEqual(alert.level, AlertLevel.RED)

    def test_read_region_alert_carries_the_reason_of_the_level_it_chose(self):
        alert = read_region_alert([self.build_kyiv("Yellow", "Red")], "м. Київ")

        self.assertEqual(alert.reason, "Red рівень")

    def test_read_region_alert_with_only_yellow_stays_yellow(self):
        alert = read_region_alert([self.build_kyiv("Yellow")], "м. Київ")

        self.assertEqual(alert.level, AlertLevel.YELLOW)


class ChoosingBetweenSocketAndPollTestCase(unittest.IsolatedAsyncioTestCase):
    """
    Which of the two feeds answers, which is the question behind this module's one real failure.

    the rule used to be «trust the socket if it spoke in the last two minutes», which sounds careful and is
    wrong: the channel publishes only on change, so silence is the normal state of a quiet night. A long
    alert therefore read from the poll instead, and two services answering by turns is a machine for
    producing flips — on 29.09 the light came up a second time on a level nobody on the ground had seen.
    """

    def build_source(self) -> UkraineAlarmSource:
        source = UkraineAlarmSource(region_name="м. Київ")
        source._poll = self.refuse_to_poll
        return source

    async def refuse_to_poll(self):
        self.polled = True
        return AirAlert(level=AlertLevel.NONE, source="poll")

    def setUp(self):
        self.polled = False

    async def test_read_current_trusts_an_open_socket_however_long_it_has_been_quiet(self):
        source = self.build_source()
        source._connected = True
        source._alert = AirAlert(level=AlertLevel.RED)

        alert = await source.read_current()

        self.assertEqual(alert.level, AlertLevel.RED)
        self.assertFalse(self.polled)

    async def test_read_current_marks_the_socket_as_the_source(self):
        source = self.build_source()
        source._connected = True
        source._alert = AirAlert(level=AlertLevel.RED)

        alert = await source.read_current()

        self.assertEqual(alert.source, "socket")

    async def test_read_current_polls_when_the_socket_is_shut(self):
        source = self.build_source()
        source._connected = False
        source._alert = AirAlert(level=AlertLevel.RED)

        alert = await source.read_current()

        self.assertTrue(self.polled)
        self.assertEqual(alert.source, "poll")

    async def test_read_current_polls_when_the_socket_has_never_said_a_level(self):
        """A fresh connection carries no baseline of its own — it only publishes what changes next."""
        source = self.build_source()
        source._connected = True
        source._alert = None

        await source.read_current()

        self.assertTrue(self.polled)
