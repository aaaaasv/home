import unittest

from src.bot.handlers.plants.care_card_reference import (
    CareCardReference,
    build_care_card_reference,
    parse_care_card_reference,
)
from src.common.constants import CareTaskType


class CareCardReferenceTestCase(unittest.TestCase):
    def test_parse_care_card_reference_reads_back_what_build_wrote(self):
        reference = build_care_card_reference(12, [CareTaskType.PHOTO, CareTaskType.WATERING])

        parsed = parse_care_card_reference(reference)

        self.assertEqual(parsed, CareCardReference(plant_id=12, task_types=frozenset({"photo", "watering"})))

    def test_build_care_card_reference_for_a_settled_card_has_an_empty_mask(self):
        reference = build_care_card_reference(12, [])

        self.assertEqual(reference, "12:0")

    def test_build_care_card_reference_with_every_task_type_fits_the_tracker_column(self):
        reference = build_care_card_reference(999999, list(CareTaskType))

        self.assertEqual((reference, len(reference) <= 32), ("999999:127", True))

    def test_parse_care_card_reference_for_a_settled_card_lists_no_needs(self):
        parsed = parse_care_card_reference("12:0")

        self.assertEqual(parsed, CareCardReference(plant_id=12, task_types=frozenset()))

    def test_parse_care_card_reference_for_the_one_card_per_task_format_is_unreadable(self):
        parsed = parse_care_card_reference("watering:5")

        self.assertIsNone(parsed)

    def test_parse_care_card_reference_for_a_missing_reference_is_unreadable(self):
        parsed = parse_care_card_reference(None)

        self.assertIsNone(parsed)
