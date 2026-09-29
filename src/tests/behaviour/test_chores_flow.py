from datetime import date

from aiogram.types import ForceReply

from src.bot.handlers.chores.keyboards import ChoreAction, ChoreCallback
from src.modules.family.use_cases.record_family_member import RecordFamilyMemberUseCase
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.telegram import CHORES_TOPIC, callback_update, message_update

MARTA_ID = 900000002


class ChoresFlowTestCase(BaseBehaviourTestCase):
    """A button pressed on a chore's menu, all the way through to the record it changes."""

    async def add_parcel_chore(self) -> int:
        await self.feed(message_update("забрати посилку", update_id=1, topic=CHORES_TOPIC))
        async with self.uow as uow:
            chores = await uow.chores.list_all()
        return chores[0].id

    def tap(self, action: ChoreAction, chore_id: int, assignee_id: int = 0, update_id: int = 2):
        payload = ChoreCallback(action=action, chore_id=chore_id, assignee_id=assignee_id).pack()
        return callback_update(payload, update_id=update_id, topic=CHORES_TOPIC)

    async def test_deadline_button_asks_for_the_date_with_a_force_reply_and_the_answer_sets_it(self):
        chore_id = await self.add_parcel_chore()
        self.session.calls.clear()

        await self.feed(self.tap(ChoreAction.DEADLINE, chore_id))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertEqual(
            prompt.reply_markup, ForceReply(selective=True, input_field_placeholder="31.07, завтра або до пʼятниці")
        )
        await self.feed(message_update("31.07", update_id=3, topic=CHORES_TOPIC))
        async with self.uow as uow:
            chores = await uow.chores.list_all()
        self.assertEqual([chore.due_on for chore in chores], [date(2026, 7, 31)])

    async def test_rename_button_asks_for_the_new_name_with_a_force_reply(self):
        chore_id = await self.add_parcel_chore()

        await self.feed(self.tap(ChoreAction.RENAME, chore_id))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertEqual(prompt.reply_markup, ForceReply(selective=True, input_field_placeholder="нова назва"))

    async def test_assignee_button_opens_the_picker_in_place_instead_of_posting_a_new_message(self):
        chore_id = await self.add_parcel_chore()
        await RecordFamilyMemberUseCase(uow=self.uow)(MARTA_ID, "Марта")
        self.session.calls.clear()

        await self.feed(self.tap(ChoreAction.ASSIGN_MENU, chore_id))

        self.assertEqual(len(self.session.calls_named("EditMessageReplyMarkup")), 1)
        self.assertEqual(self.session.calls_named("SendMessage"), [])
        self.assertEqual(self.session.calls_named("DeleteMessage"), [])

    async def test_picking_an_assignee_closes_the_picker_in_place_and_tags_the_chore(self):
        chore_id = await self.add_parcel_chore()
        await RecordFamilyMemberUseCase(uow=self.uow)(MARTA_ID, "Марта")
        self.session.calls.clear()

        await self.feed(self.tap(ChoreAction.ASSIGN, chore_id, assignee_id=MARTA_ID))

        edits = self.session.calls_named("EditMessageReplyMarkup")
        self.assertEqual(len(edits), 1)
        self.assertEqual(
            [button.text for row in edits[0].reply_markup.inline_keyboard for button in row],
            ["Зроблено", "Дата", "Чия", "Перейменувати", "Прибрати", "← Назад"],
        )
        self.assertEqual(self.session.calls_named("DeleteMessage"), [])
        async with self.uow as uow:
            chores = await uow.chores.list_all()
        self.assertEqual([chore.assignee_display_name for chore in chores], ["Марта"])
