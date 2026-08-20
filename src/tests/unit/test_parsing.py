import unittest

from src.modules.plant_care.services.care_input_parser import parse_interval_days


class ParseIntervalDaysTestCase(unittest.TestCase):
    def test_parse_interval_days_within_the_allowed_range_returns_the_number(self):
        self.assertEqual(parse_interval_days("1"), 1)
        self.assertEqual(parse_interval_days("45"), 45)
        self.assertEqual(parse_interval_days(" 90 "), 90)
        self.assertEqual(parse_interval_days("1095"), 1095)

    def test_parse_interval_days_outside_the_allowed_range_returns_none(self):
        self.assertIsNone(parse_interval_days("0"))
        self.assertIsNone(parse_interval_days("1096"))

    def test_parse_interval_days_of_a_non_number_returns_none(self):
        self.assertIsNone(parse_interval_days("сім"))
        self.assertIsNone(parse_interval_days("7 днів"))
        self.assertIsNone(parse_interval_days("-7"))
        self.assertIsNone(parse_interval_days(""))
