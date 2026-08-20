from datetime import date, datetime, timedelta, timezone

from src.common.domain import Actor
from src.modules.chores.commands import (
    AddChoreCommand,
    CompleteChoreCommand,
    RemoveChoreCommand,
    SetChoreDeadlineCommand,
)
from src.modules.chores.use_cases.add_chore import AddChoreUseCase
from src.modules.chores.use_cases.complete_chore import CompleteChoreUseCase
from src.modules.chores.use_cases.evaluate_chore_deadlines import EvaluateChoreDeadlinesUseCase
from src.modules.chores.use_cases.remove_chore import RemoveChoreUseCase
from src.modules.chores.use_cases.set_chore_deadline import SetChoreDeadlineUseCase
from src.tests.integration.base import BaseIntegrationTestCase

BOHDAN = Actor(telegram_user_id=1, display_name="Богдан")
TODAY = date(2026, 7, 28)


class ChoresTestCase(BaseIntegrationTestCase):
    async def add_chore(self, name: str, due_on: date | None = None):
        return await AddChoreUseCase(uow=self.uow, actor=BOHDAN)(AddChoreCommand(name=name, due_on=due_on))

    async def test_add_chore_without_a_date_lands_in_the_someday_pile(self):
        chores = await self.add_chore("почистити ноутбук")

        self.assertEqual([chore.name for chore in chores.someday], ["почистити ноутбук"])
        self.assertEqual(chores.dated, [])

    async def test_add_chore_with_a_date_lands_in_the_dated_list(self):
        chores = await self.add_chore("забрати негативи", due_on=date(2026, 7, 31))

        self.assertEqual(len(chores.dated), 1)
        self.assertEqual(chores.dated[0].name, "забрати негативи")
        self.assertEqual(chores.dated[0].due_on, date(2026, 7, 31))
        self.assertEqual(chores.someday, [])

    async def test_add_the_same_chore_twice_keeps_only_the_first(self):
        await self.add_chore("помити вікна")

        chores = await self.add_chore("Помити Вікна")

        self.assertEqual([chore.name for chore in chores.someday], ["помити вікна"])

    async def test_complete_chore_drops_it_from_the_open_list(self):
        chores = await self.add_chore("винести сміття")

        result = await CompleteChoreUseCase(uow=self.uow, actor=BOHDAN, completed_at=datetime.now(timezone.utc))(
            CompleteChoreCommand(chore_id=chores.someday[0].id)
        )

        self.assertTrue(result.is_empty)

    async def test_set_chore_deadline_moves_it_from_someday_to_dated(self):
        chores = await self.add_chore("забрати негативи")

        result = await SetChoreDeadlineUseCase(uow=self.uow)(
            SetChoreDeadlineCommand(chore_id=chores.someday[0].id, due_on=date(2026, 7, 31))
        )

        self.assertEqual(result.someday, [])
        self.assertEqual(len(result.dated), 1)
        self.assertEqual(result.dated[0].due_on, date(2026, 7, 31))

    async def test_clear_chore_deadline_moves_it_back_to_someday(self):
        chores = await self.add_chore("забрати негативи", due_on=date(2026, 7, 31))

        result = await SetChoreDeadlineUseCase(uow=self.uow)(
            SetChoreDeadlineCommand(chore_id=chores.dated[0].id, due_on=None)
        )

        self.assertEqual(result.dated, [])
        self.assertEqual([chore.name for chore in result.someday], ["забрати негативи"])

    async def test_remove_chore_deletes_it_entirely(self):
        chores = await self.add_chore("помилковий запис")

        result = await RemoveChoreUseCase(uow=self.uow)(RemoveChoreCommand(chore_id=chores.someday[0].id))

        self.assertTrue(result.is_empty)

    async def test_evaluate_chore_deadlines_returns_only_chores_inside_the_lead_window(self):
        await self.add_chore("далеко", due_on=TODAY + timedelta(days=10))
        await self.add_chore("завтра", due_on=TODAY + timedelta(days=1))
        await self.add_chore("колись")

        reminders = await EvaluateChoreDeadlinesUseCase(uow=self.uow, today=TODAY, lead_days=1)()

        self.assertEqual([(reminder.name, reminder.days_until_due) for reminder in reminders], [("завтра", 1)])

    async def test_evaluate_chore_deadlines_includes_overdue_and_orders_by_due_date(self):
        await self.add_chore("сьогодні", due_on=TODAY)
        await self.add_chore("позавчора", due_on=TODAY - timedelta(days=2))

        reminders = await EvaluateChoreDeadlinesUseCase(uow=self.uow, today=TODAY, lead_days=1)()

        self.assertEqual(
            [(reminder.name, reminder.days_until_due) for reminder in reminders], [("позавчора", -2), ("сьогодні", 0)]
        )

    async def test_evaluate_chore_deadlines_excludes_a_completed_chore(self):
        chores = await self.add_chore("зроблено", due_on=TODAY)
        await CompleteChoreUseCase(uow=self.uow, actor=BOHDAN, completed_at=datetime.now(timezone.utc))(
            CompleteChoreCommand(chore_id=chores.dated[0].id)
        )

        reminders = await EvaluateChoreDeadlinesUseCase(uow=self.uow, today=TODAY, lead_days=1)()

        self.assertEqual(reminders, [])
