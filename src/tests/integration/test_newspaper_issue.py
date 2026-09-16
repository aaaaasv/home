from datetime import timedelta

from src.modules.newspaper.domain import CrosswordClue
from src.modules.newspaper.services.word_source import WordBank
from src.modules.newspaper.use_cases.mark_issue_printed import MarkIssuePrintedUseCase
from src.modules.newspaper.use_cases.prepare_issue import PrepareIssueUseCase
from src.tests.fakes import FrozenHouseholdCalendar, ScriptedWordSource
from src.tests.integration.base import FROZEN_NOW, KYIV, BaseIntegrationTestCase


class PrepareIssueTestCase(BaseIntegrationTestCase):
    def build_use_case(self, word_sources=None, household_calendar=None) -> PrepareIssueUseCase:
        return PrepareIssueUseCase(
            uow=self.uow,
            household_calendar=household_calendar or self.household_calendar,
            word_sources=word_sources if word_sources is not None else [WordBank()],
        )

    def calendar_weeks_later(self, weeks: int) -> FrozenHouseholdCalendar:
        return FrozenHouseholdCalendar(timezone=KYIV, frozen_now=FROZEN_NOW + timedelta(weeks=weeks))

    async def test_prepare_issue_for_the_first_week_numbers_it_one_and_starts_it_on_monday(self):
        use_case = self.build_use_case()

        issue = await use_case()

        # FROZEN_NOW is sunday 12 july 2026, so its week began on monday the 6th
        self.assertEqual((issue.number, issue.week_starts_on.isoformat()), (1, "2026-07-06"))
        self.assertGreaterEqual(len(issue.crossword.entries), 12)

    async def test_prepare_issue_twice_in_one_week_returns_the_same_crossword_both_times(self):
        first = await self.build_use_case()()

        second = await self.build_use_case()()

        self.assertEqual(second, first)

    async def test_prepare_issue_once_the_week_has_printed_returns_nothing(self):
        issue = await self.build_use_case()()
        await MarkIssuePrintedUseCase(uow=self.uow, household_calendar=self.household_calendar)(issue.id)

        again = await self.build_use_case()()

        self.assertIsNone(again)

    async def test_prepare_issue_the_next_week_numbers_it_two_and_reuses_none_of_last_weeks_words(self):
        first = await self.build_use_case()()
        await MarkIssuePrintedUseCase(uow=self.uow, household_calendar=self.household_calendar)(first.id)

        second = await self.build_use_case(household_calendar=self.calendar_weeks_later(1))()

        self.assertEqual(second.number, 2)
        last_weeks_words = {entry.answer for entry in first.crossword.entries}
        this_weeks_words = {entry.answer for entry in second.crossword.entries}
        self.assertEqual(last_weeks_words & this_weeks_words, set())

    async def test_prepare_issue_the_next_week_asks_every_source_to_leave_out_last_weeks_words(self):
        first = await self.build_use_case()()
        await MarkIssuePrintedUseCase(uow=self.uow, household_calendar=self.household_calendar)(first.id)
        fresh_source = ScriptedWordSource([])

        await self.build_use_case(
            word_sources=[fresh_source, WordBank()], household_calendar=self.calendar_weeks_later(1)
        )()

        self.assertEqual(fresh_source.excluded_requests, [{entry.answer for entry in first.crossword.entries}])

    async def test_prepare_issue_with_an_empty_first_source_is_built_from_the_bank_alone(self):
        use_case = self.build_use_case(word_sources=[ScriptedWordSource([]), WordBank()])

        issue = await use_case()

        bank_answers = {clue.answer for clue in WordBank().read_all()}
        self.assertTrue({entry.answer for entry in issue.crossword.entries} <= bank_answers)

    async def test_prepare_issue_drops_offered_words_that_break_the_grid_rules(self):
        broken = [
            CrosswordClue(answer="М'ЯТА", clue="Запашна трава для чаю"),
            CrosswordClue(answer="КОВАЛЬ", clue="Майстер біля ковадла"),
        ]
        use_case = self.build_use_case(word_sources=[ScriptedWordSource(broken), WordBank()])

        issue = await use_case()

        self.assertEqual({"М'ЯТА", "КОВАЛЬ"} & {entry.answer for entry in issue.crossword.entries}, set())
