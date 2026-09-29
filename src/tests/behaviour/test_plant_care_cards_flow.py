from unittest.mock import patch

from aiogram.methods import EditMessageCaption, EditMessageText
from aiogram.types import ForceReply

from src.bot.handlers.plants import messages, photos
from src.bot.handlers.plants.care_card_reference import build_care_card_reference
from src.bot.services.posted_message_tracker import CARE_DIGEST_KIND
from src.common.constants import CareTaskType
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.telegram import ACTOR_ID, ASKER_MENTION, CHAT_ID, callback_update, message_update, photo_update

STANDING_CARD_MESSAGE_ID = 77


class PlantCareCardsFlowTestCase(BaseBehaviourTestCase):
    """
    Recording, deferring and photographing through the real dispatcher, from both kinds of card.

    the plant's own card is a page somebody opened on purpose and must stay a page; the digest card is one plant's
    to-do list and shrinks as the list does. the two are told apart only by what the button's payload says.
    """

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Містер Біг")
        async with self.uow as uow:
            await uow.family_members.upsert(ACTOR_ID, "Тест")

    async def seed_due_task(self, task_type: CareTaskType) -> None:
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=task_type, interval_days=7, next_due_on=self.today
        )

    async def stand_card(self, *task_types: CareTaskType, message_id: int = STANDING_CARD_MESSAGE_ID) -> None:
        async with self.uow as uow:
            await uow.posted_messages.create(
                {
                    "kind": CARE_DIGEST_KIND,
                    "chat_id": CHAT_ID,
                    "message_id": message_id,
                    "reference": build_care_card_reference(self.plant_id, task_types),
                }
            )

    async def list_standing_references(self) -> list[tuple[int, str]]:
        async with self.uow as uow:
            tracked = await uow.posted_messages.list_by_kind(CARE_DIGEST_KIND)
        return [(posted.message_id, posted.reference) for posted in tracked]

    def button_texts(self, edit: EditMessageText | EditMessageCaption) -> list[list[str]]:
        return [[button.text for button in row] for row in edit.reply_markup.inline_keyboard]

    def edits(self) -> list[EditMessageText | EditMessageCaption]:
        return [*self.session.calls_named("EditMessageText"), *self.session.calls_named("EditMessageCaption")]

    async def test_record_care_from_the_plant_card_redraws_the_card_in_place(self):
        await self.seed_due_task(CareTaskType.WATERING)
        await self.seed_due_task(CareTaskType.FERTILIZING)

        await self.feed(callback_update(f"care:{self.plant_id}:watering:0:1"))

        self.assertEqual(
            (
                len(self.edits()),
                self.session.calls_named("SendMessage"),
                self.session.calls_named("DeleteMessage"),
            ),
            (1, [], []),
        )

    async def test_record_care_from_the_plant_card_keeps_the_page_and_writes_the_record_into_its_history(self):
        await self.seed_due_task(CareTaskType.WATERING)

        await self.feed(callback_update(f"care:{self.plant_id}:watering:0:1"))

        text = self.edits()[0].text
        self.assertEqual(
            (text.startswith("🪴 <b>Містер Біг</b>"), "<b>Догляд</b>" in text, "— полив · Тест" in text),
            (True, True, True),
        )

    async def test_record_care_from_the_plant_card_takes_only_the_recorded_button_off(self):
        await self.seed_due_task(CareTaskType.WATERING)
        await self.seed_due_task(CareTaskType.FERTILIZING)

        await self.feed(callback_update(f"care:{self.plant_id}:watering:0:1"))

        self.assertEqual(
            self.button_texts(self.edits()[0]),
            [["Підживлено"], ["Додати фото"], ["Додати догляд", "Змінити", "Прибрати"], ["До списку"]],
        )

    async def test_record_care_from_the_plant_card_rewrites_the_standing_digest_card_without_the_task(self):
        await self.seed_due_task(CareTaskType.WATERING)
        await self.seed_due_task(CareTaskType.FERTILIZING)
        await self.stand_card(CareTaskType.WATERING, CareTaskType.FERTILIZING)

        await self.feed(callback_update(f"care:{self.plant_id}:watering:0:1"))

        standing_edit = next(edit for edit in self.edits() if edit.message_id == STANDING_CARD_MESSAGE_ID)
        self.assertEqual(
            (standing_edit.text, await self.list_standing_references()),
            (
                "🪴 <b>Містер Біг</b>\n🌱 добриво",
                [(STANDING_CARD_MESSAGE_ID, build_care_card_reference(self.plant_id, [CareTaskType.FERTILIZING]))],
            ),
        )

    async def test_record_care_from_the_plant_card_deletes_the_standing_digest_card_when_nothing_is_left(self):
        await self.seed_due_task(CareTaskType.WATERING)
        await self.stand_card(CareTaskType.WATERING)

        await self.feed(callback_update(f"care:{self.plant_id}:watering:0:1"))

        deleted_ids = [call.message_id for call in self.session.calls_named("DeleteMessage")]
        self.assertEqual((deleted_ids, await self.list_standing_references()), ([STANDING_CARD_MESSAGE_ID], []))

    async def test_record_care_from_a_digest_card_with_another_task_due_shrinks_the_card(self):
        await self.seed_due_task(CareTaskType.WATERING)
        await self.seed_due_task(CareTaskType.FERTILIZING)
        await self.stand_card(CareTaskType.WATERING, CareTaskType.FERTILIZING, message_id=1)

        await self.feed(callback_update(f"care:{self.plant_id}:watering:0:0", message_id=1))

        edit = self.edits()[0]
        self.assertEqual(
            (edit.text, self.button_texts(edit), await self.list_standing_references()),
            (
                "🪴 <b>Містер Біг</b>\n🌱 добриво",
                [["Підживлено", "Відкласти"]],
                [(1, build_care_card_reference(self.plant_id, [CareTaskType.FERTILIZING]))],
            ),
        )

    async def test_record_care_from_a_digest_card_with_nothing_else_due_leaves_a_receipt_with_an_undo(self):
        await self.seed_due_task(CareTaskType.WATERING)
        await self.stand_card(CareTaskType.WATERING, message_id=1)

        await self.feed(callback_update(f"care:{self.plant_id}:watering:0:0", message_id=1))

        edit = self.edits()[0]
        self.assertEqual(
            (edit.text, self.button_texts(edit), await self.list_standing_references()),
            (
                "✅ <b>Містер Біг</b> — 💧 полито\n<i>Тест, 09:00</i>",
                [["Скасувати"]],
                [(1, build_care_card_reference(self.plant_id, []))],
            ),
        )

    async def test_undo_care_on_a_receipt_brings_the_grouped_card_back(self):
        await self.seed_due_task(CareTaskType.WATERING)
        await self.seed_due_task(CareTaskType.FERTILIZING)
        await self.feed(callback_update(f"care:{self.plant_id}:watering:0:0", message_id=1))
        self.session.calls.clear()

        await self.feed(callback_update(f"schedule:undo:{self.plant_id}:watering:0", message_id=1))

        edit = self.edits()[0]
        self.assertEqual(
            (edit.text, self.button_texts(edit)),
            ("🪴 <b>Містер Біг</b>\n💧 полив\n🌱 добриво", [["Полито", "Відкласти"], ["Підживлено", "Відкласти"]]),
        )

    async def test_postpone_care_with_another_task_due_keeps_the_card_with_that_task(self):
        await self.seed_due_task(CareTaskType.WATERING)
        await self.seed_due_task(CareTaskType.FERTILIZING)

        await self.feed(callback_update(f"schedule:postpone:{self.plant_id}:watering:0"))

        edit = self.edits()[0]
        self.assertEqual((edit.text, self.session.calls_named("DeleteMessage")), ("🪴 <b>Містер Біг</b>\n🌱 добриво", []))

    async def test_postpone_care_with_nothing_else_due_deletes_the_card(self):
        await self.seed_due_task(CareTaskType.WATERING)
        await self.stand_card(CareTaskType.WATERING, message_id=1)

        await self.feed(callback_update(f"schedule:postpone:{self.plant_id}:watering:0", message_id=1))

        deleted_ids = [call.message_id for call in self.session.calls_named("DeleteMessage")]
        self.assertEqual((self.edits(), set(deleted_ids), await self.list_standing_references()), ([], {1}, []))

    async def test_record_care_from_the_plant_card_within_the_guard_window_asks_before_repeating_it(self):
        await self.seed_due_task(CareTaskType.WATERING)
        await self.feed(callback_update(f"care:{self.plant_id}:watering:0:1"))
        self.session.calls.clear()

        await self.feed(callback_update(f"care:{self.plant_id}:watering:0:1", update_id=2))

        warning = self.session.calls_named("SendMessage")[0]
        self.assertEqual(warning.reply_markup.inline_keyboard[0][0].callback_data, f"care:{self.plant_id}:watering:1:1")

    async def test_record_care_from_the_plant_card_after_confirming_the_warning_sends_the_page_again(self):
        await self.seed_due_task(CareTaskType.WATERING)
        await self.feed(callback_update(f"care:{self.plant_id}:watering:0:1"))
        self.session.calls.clear()

        await self.feed(callback_update(f"care:{self.plant_id}:watering:1:1", update_id=2, message_id=5))

        sent = self.session.calls_named("SendMessage")
        self.assertEqual(
            ([call.message_id for call in self.session.calls_named("DeleteMessage")], len(sent), self.edits()),
            ([5], 1, []),
        )

    async def test_add_photo_from_an_old_digest_card_button_still_opens_the_upload(self):
        await self.feed(callback_update(f"plant:photo_due:{self.plant_id}"))

        self.assertEqual(self.session.sent_texts(), [messages.ADD_PHOTO_ASK_PHOTO])

    async def test_add_photo_takes_the_photo_line_off_the_standing_card(self):
        await self.seed_due_task(CareTaskType.WATERING)
        await self.seed_due_task(CareTaskType.PHOTO)
        await self.stand_card(CareTaskType.WATERING, CareTaskType.PHOTO)
        await self.feed(callback_update(f"plant:photo_due:{self.plant_id}"))

        with patch.object(photos, "ALBUM_SETTLE_SECONDS", 0.01):
            await self.feed(photo_update("first", update_id=10))
            await photos._open_sessions[(CHAT_ID, ACTOR_ID)].closing

        standing_edit = next(edit for edit in self.edits() if edit.message_id == STANDING_CARD_MESSAGE_ID)
        self.assertEqual(
            (standing_edit.caption, self.button_texts(standing_edit)),
            ("🪴 <b>Містер Біг</b>\n💧 полив", [["Полито", "Відкласти"]]),
        )

    async def test_add_plant_asks_for_the_name_in_a_field_that_opens_itself_for_the_asker_only(self):
        await self.feed(message_update("/add"))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertEqual(
            (prompt.text, prompt.reply_markup),
            (
                ASKER_MENTION + messages.ADD_PLANT_ASK_NAME,
                ForceReply(selective=True, input_field_placeholder="Назва рослини"),
            ),
        )

    async def test_edit_plant_asks_for_the_new_value_in_a_field_that_opens_itself(self):
        await self.feed(callback_update(f"edit_plant:{self.plant_id}:notes"))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertEqual(prompt.reply_markup, ForceReply(selective=True, input_field_placeholder="Нотатка"))

    async def test_custom_interval_asks_for_the_days_in_a_field_that_opens_itself(self):
        await self.seed_due_task(CareTaskType.WATERING)

        await self.feed(callback_update(f"schedule:set:{self.plant_id}:watering:0"))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertEqual(prompt.reply_markup, ForceReply(selective=True, input_field_placeholder="Число днів"))

    async def test_care_instructions_are_asked_for_in_a_field_that_opens_itself(self):
        await self.seed_due_task(CareTaskType.WATERING)

        await self.feed(callback_update(f"schedule:instructions:{self.plant_id}:watering:0"))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertEqual(prompt.reply_markup, ForceReply(selective=True, input_field_placeholder="Як саме робити"))

    async def test_set_schedule_with_a_preset_interval_sends_the_plant_card_again(self):
        await self.seed_due_task(CareTaskType.WATERING)

        await self.feed(callback_update(f"schedule:set:{self.plant_id}:watering:14"))

        sent_texts = [call.text for call in self.session.calls_named("SendMessage")]
        self.assertEqual([text.startswith("🪴 <b>Містер Біг</b>") for text in sent_texts], [True])
