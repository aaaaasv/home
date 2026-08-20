import unittest
from datetime import date, timedelta

from src.modules.chores.services.deadline_parser import parse_chore_text, parse_deadline, split_assignee
from src.modules.family.domain import FamilyMember

# a tuesday, chosen so «до 15.01» is unambiguously next year and weekday maths has somewhere to roll to
TODAY = date(2026, 7, 28)
MEMBERS = [
    FamilyMember(telegram_user_id=1, display_name="Марта Пупкіна"),
    FamilyMember(telegram_user_id=2, display_name="Богдан"),
]


class ParseChoreTextTestCase(unittest.TestCase):
    def test_parse_chore_text_lifts_an_absolute_deadline_marked_with_do(self):
        name, due_on = parse_chore_text("забрати негативи до 31.07", TODAY)

        self.assertEqual(name, "забрати негативи")
        self.assertEqual(due_on, date(2026, 7, 31))

    def test_parse_chore_text_with_an_explicit_year_keeps_it(self):
        name, due_on = parse_chore_text("продовжити страховку до 05.08.2027", TODAY)

        self.assertEqual(name, "продовжити страховку")
        self.assertEqual(due_on, date(2027, 8, 5))

    def test_parse_chore_text_rolls_a_past_bare_date_to_next_year(self):
        name, due_on = parse_chore_text("подарунки до 15.01", TODAY)

        self.assertEqual(name, "подарунки")
        self.assertEqual(due_on, date(2027, 1, 15))

    def test_parse_chore_text_without_a_deadline_returns_no_date(self):
        name, due_on = parse_chore_text("почистити ноутбук", TODAY)

        self.assertEqual(name, "почистити ноутбук")
        self.assertIsNone(due_on)

    def test_parse_chore_text_leaves_a_date_in_the_title_when_it_is_not_a_deadline(self):
        name, due_on = parse_chore_text("купити подарунок на 8 березня", TODAY)

        self.assertEqual(name, "купити подарунок на 8 березня")
        self.assertIsNone(due_on)

    def test_parse_chore_text_reads_zavtra(self):
        name, due_on = parse_chore_text("подзвонити майстру завтра", TODAY)

        self.assertEqual(name, "подзвонити майстру")
        self.assertEqual(due_on, TODAY + timedelta(days=1))

    def test_parse_chore_text_reads_a_relative_count_in_weeks(self):
        name, due_on = parse_chore_text("здати звіт через 2 тижні", TODAY)

        self.assertEqual(name, "здати звіт")
        self.assertEqual(due_on, TODAY + timedelta(days=14))

    def test_parse_chore_text_reads_a_weekday_as_the_next_occurrence(self):
        name, due_on = parse_chore_text("записати авто до пʼятниці", TODAY)

        self.assertEqual(name, "записати авто")
        self.assertEqual(due_on.weekday(), 4)
        self.assertTrue(TODAY <= due_on < TODAY + timedelta(days=7))

    def test_parse_chore_text_ignores_an_impossible_date(self):
        name, due_on = parse_chore_text("здати щось до 31.02", TODAY)

        self.assertEqual(name, "здати щось до 31.02")
        self.assertIsNone(due_on)


class ParseDeadlineTestCase(unittest.TestCase):
    def test_parse_deadline_reads_a_bare_date(self):
        self.assertEqual(parse_deadline("31.07", TODAY), date(2026, 7, 31))

    def test_parse_deadline_reads_a_bare_relative_word(self):
        self.assertEqual(parse_deadline("завтра", TODAY), TODAY + timedelta(days=1))

    def test_parse_deadline_returns_none_for_gibberish(self):
        self.assertIsNone(parse_deadline("колись потім", TODAY))


class SplitAssigneeTestCase(unittest.TestCase):
    def test_split_assignee_tags_a_leading_known_first_name(self):
        member, remainder = split_assignee("Марта забрати посилку до 31.07", MEMBERS)

        self.assertEqual(member.telegram_user_id, 1)
        self.assertEqual(remainder, "забрати посилку до 31.07")

    def test_split_assignee_accepts_a_separator_after_the_name(self):
        member, remainder = split_assignee("Богдан: полити гриби", MEMBERS)

        self.assertEqual(member.telegram_user_id, 2)
        self.assertEqual(remainder, "полити гриби")

    def test_split_assignee_matches_the_first_name_case_insensitively(self):
        member, remainder = split_assignee("марта купити молоко", MEMBERS)

        self.assertEqual(member.telegram_user_id, 1)
        self.assertEqual(remainder, "купити молоко")

    def test_split_assignee_ignores_an_unknown_first_word(self):
        member, remainder = split_assignee("забрати посилку", MEMBERS)

        self.assertIsNone(member)
        self.assertEqual(remainder, "забрати посилку")
