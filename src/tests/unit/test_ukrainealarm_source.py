import unittest

from src.infrastructure.adapters.ukrainealarm_source import read_region_alert
from src.modules.air_alert.domain import AlertLevel

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
