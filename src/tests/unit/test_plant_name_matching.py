import unittest

from src.bot.handlers.plants.tools import match_plant_name

NAMES = ["Принцеса", "Тігл", "Бубик", "Пеперомія", "Пепероні", "Марті", "Мартін"]


class MatchPlantNameTestCase(unittest.TestCase):
    """
    Finding the plant somebody just said the name of, in a language that declines the name.

    the family says «сорт принцеси» and «полив тігла», never the nominative the card is filed under, so an
    exact match alone would answer «не знаходжу рослину» to every sentence anybody actually types.
    """

    def test_match_plant_name_takes_the_exact_name_as_written(self):
        self.assertEqual(match_plant_name("Принцеса", NAMES), ["Принцеса"])

    def test_match_plant_name_ignores_the_case_it_was_typed_in(self):
        self.assertEqual(match_plant_name("бубик", NAMES), ["Бубик"])

    def test_match_plant_name_reaches_the_plant_through_a_declined_ending(self):
        self.assertEqual(match_plant_name("принцеси", NAMES), ["Принцеса"])

    def test_match_plant_name_reaches_a_short_name_through_a_declined_ending(self):
        self.assertEqual(match_plant_name("тігла", NAMES), ["Тігл"])

    def test_match_plant_name_returns_both_namesakes_rather_than_picking_one(self):
        self.assertEqual(match_plant_name("мартіна", NAMES), ["Марті", "Мартін"])

    def test_match_plant_name_keeps_two_similar_names_apart_when_more_than_an_ending_differs(self):
        self.assertEqual(match_plant_name("пеперомії", NAMES), ["Пеперомія"])

    def test_match_plant_name_with_a_name_nobody_has_matches_nothing(self):
        self.assertEqual(match_plant_name("Фікус", NAMES), [])

    def test_match_plant_name_does_not_let_a_short_shared_start_match(self):
        self.assertEqual(match_plant_name("Тінь", NAMES), [])

    def test_match_plant_name_with_blank_text_matches_nothing(self):
        self.assertEqual(match_plant_name("   ", NAMES), [])
