from datetime import date

from src.common.domain import Actor
from src.modules.chores.commands import AddChoreCommand, SetChoreAssigneeCommand
from src.modules.chores.use_cases.add_chore import AddChoreUseCase
from src.modules.chores.use_cases.set_chore_assignee import SetChoreAssigneeUseCase
from src.modules.family.use_cases.list_family_members import ListFamilyMembersUseCase
from src.modules.family.use_cases.record_family_member import RecordFamilyMemberUseCase
from src.tests.integration.base import BaseIntegrationTestCase

BOHDAN = Actor(telegram_user_id=1, display_name="Богдан")


class FamilyRosterTestCase(BaseIntegrationTestCase):
    async def test_record_family_member_remembers_id_and_first_name(self):
        await RecordFamilyMemberUseCase(uow=self.uow)(1, "Богдан")
        await RecordFamilyMemberUseCase(uow=self.uow)(2, "Марта Пупкіна")

        members = await ListFamilyMembersUseCase(uow=self.uow)()

        self.assertEqual(
            [(member.telegram_user_id, member.first_name) for member in members], [(1, "Богдан"), (2, "Марта")]
        )

    async def test_record_family_member_twice_updates_the_name_without_duplicating(self):
        await RecordFamilyMemberUseCase(uow=self.uow)(1, "Богдан")

        await RecordFamilyMemberUseCase(uow=self.uow)(1, "Богдан Новий")

        members = await ListFamilyMembersUseCase(uow=self.uow)()
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].display_name, "Богдан Новий")

    async def test_add_chore_with_an_assignee_stores_the_person(self):
        chores = await AddChoreUseCase(uow=self.uow, actor=BOHDAN)(
            AddChoreCommand(
                name="забрати посилку",
                due_on=date(2026, 7, 31),
                assignee_telegram_user_id=2,
                assignee_display_name="Марта",
            )
        )

        self.assertEqual(chores.dated[0].assignee_telegram_user_id, 2)
        self.assertEqual(chores.dated[0].assignee_display_name, "Марта")

    async def test_set_chore_assignee_then_clearing_it_removes_the_person(self):
        chores = await AddChoreUseCase(uow=self.uow, actor=BOHDAN)(AddChoreCommand(name="прибрати"))
        chore_id = chores.someday[0].id

        assigned = await SetChoreAssigneeUseCase(uow=self.uow)(
            SetChoreAssigneeCommand(chore_id=chore_id, assignee_telegram_user_id=2, assignee_display_name="Марта")
        )
        cleared = await SetChoreAssigneeUseCase(uow=self.uow)(
            SetChoreAssigneeCommand(chore_id=chore_id, assignee_telegram_user_id=None, assignee_display_name=None)
        )

        self.assertEqual(assigned.someday[0].assignee_display_name, "Марта")
        self.assertIsNone(cleared.someday[0].assignee_telegram_user_id)
        self.assertIsNone(cleared.someday[0].assignee_display_name)
