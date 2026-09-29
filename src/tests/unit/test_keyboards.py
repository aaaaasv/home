import re
import unittest
from datetime import date, datetime, timezone

from src.bot.handlers.places.keyboards import build_place_item_keyboard, build_places_list_keyboard
from src.bot.handlers.plants.keyboards import (
    build_archive_confirmation_keyboard,
    build_archived_plant_keyboard,
    build_care_cards,
    build_force_care_keyboard,
    build_new_plant_interval_keyboard,
    build_plant_card_keyboard,
    build_plant_edit_keyboard,
    build_plant_list_keyboard,
    build_recorded_care_keyboard,
    build_schedule_interval_keyboard,
    build_schedule_remove_keyboard,
    build_task_type_keyboard,
    find_recorded_task_types,
)
from src.bot.handlers.shopping.keyboards import build_shopping_item_keyboard, build_shopping_list_keyboard
from src.common.constants import MAXIMUM_CARE_INTERVAL_DAYS, CareTaskType
from src.modules.places.domain import PlaceDetails, PlacesList
from src.modules.plant_care.domain import CareDigest, CareScheduleDetails, DueCareTask, PlantCard, PlantSummary
from src.modules.shopping.constants import ShoppingHorizon
from src.modules.shopping.domain import ShoppingItemDetails, ShoppingList

# telegram rejects any callback_data above this, and an integer id is what buys us the room
CALLBACK_DATA_MAX_BYTES = 64

# the widest realistic payload: a big plant id, the longest task type, the longest interval
PLANT_ID = 999999
MOMENT = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)
# the pictographs, dingbats and arrows an emoji is drawn from, and the variation selector that turns text into one
EMOJI_PATTERN = re.compile("[\U0001F300-\U0001FAFF\u2190-\u21FF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")


def _shopping_item(horizon: ShoppingHorizon, tracked: bool) -> ShoppingItemDetails:
    return ShoppingItemDetails(
        id=PLANT_ID,
        name="Пилосос",
        horizon=horizon,
        added_by_display_name="Богдан",
        current_price=21999 if tracked else None,
        initial_price=21999 if tracked else None,
    )


def _shopping_list() -> ShoppingList:
    return ShoppingList(
        needed_now=[_shopping_item(ShoppingHorizon.NOW, tracked=False)],
        wanted_later=[_shopping_item(ShoppingHorizon.LATER, tracked=True)],
    )


def _places_list() -> PlacesList:
    place = PlaceDetails(
        id=PLANT_ID,
        name="Кафе",
        link=None,
        address=None,
        note=None,
        setting=None,
        added_by_display_name="Марта",
        visited_at=None,
        visited_by_display_name=None,
    )
    return PlacesList(to_visit=[place], visited=[])


def build_schedule(task_type: CareTaskType) -> CareScheduleDetails:
    return CareScheduleDetails(
        task_type=task_type,
        interval_days=1095,
        next_due_on=date(2026, 7, 14),
        last_performed_at=MOMENT,
        days_until_due=0,
    )


def build_card() -> PlantCard:
    return PlantCard(
        id=PLANT_ID,
        name="Непентес",
        species="Nepenthes hybrid (×ventrata)",
        location="спальня, підвіконня",
        room="спальня",
        notes="гине від жорсткої води",
        created_at=MOMENT,
        schedules=[build_schedule(task_type) for task_type in CareTaskType],
        recent_events=[],
        cover_photo=None,
        photo_count=3,
    )


class CallbackDataSizeTestCase(unittest.TestCase):
    def build_every_keyboard(self) -> list:
        card = build_card()
        digest = CareDigest(
            today=date(2026, 7, 14),
            tasks=[
                DueCareTask(
                    plant_id=PLANT_ID,
                    plant_name="Непентес",
                    task_type=task_type,
                    interval_days=MAXIMUM_CARE_INTERVAL_DAYS,
                    overdue_days=999,
                )
                for task_type in CareTaskType
            ],
        )
        summaries = [
            PlantSummary(id=PLANT_ID, name="Непентес", location="спальня", schedules=card.schedules),
        ]
        return [
            *(care_card.keyboard for care_card in build_care_cards(digest)),
            build_force_care_keyboard(PLANT_ID, CareTaskType.FERTILIZING, from_plant_card=True),
            build_plant_list_keyboard(summaries),
            build_plant_card_keyboard(card),
            build_plant_edit_keyboard(card),
            build_task_type_keyboard(card),
            build_schedule_interval_keyboard(PLANT_ID, CareTaskType.FERTILIZING),
            build_new_plant_interval_keyboard(),
            build_shopping_list_keyboard(_shopping_list()),
            build_shopping_item_keyboard(_shopping_item(ShoppingHorizon.LATER, tracked=False)),
            build_shopping_item_keyboard(_shopping_item(ShoppingHorizon.NOW, tracked=True)),
            build_places_list_keyboard(_places_list()),
            build_place_item_keyboard(_places_list().to_visit[0]),
        ]

    def test_every_button_payload_stays_under_the_telegram_cap(self):
        oversized_payloads = [
            button.callback_data
            for keyboard in self.build_every_keyboard()
            for row in keyboard.inline_keyboard
            for button in row
            if len(button.callback_data.encode()) > CALLBACK_DATA_MAX_BYTES
        ]

        self.assertEqual(oversized_payloads, [])

    def test_every_button_carries_a_payload(self):
        payloads = [
            button.callback_data
            for keyboard in self.build_every_keyboard()
            for row in keyboard.inline_keyboard
            for button in row
        ]

        self.assertTrue(all(payloads))


class CareCardKeyboardTestCase(unittest.TestCase):
    def build_task(self, task_type: CareTaskType, plant_id: int = PLANT_ID) -> DueCareTask:
        return DueCareTask(
            plant_id=plant_id, plant_name="Кактус", task_type=task_type, interval_days=30, overdue_days=0
        )

    def build_card_keyboard(self, *task_types: CareTaskType):
        digest = CareDigest(today=date(2026, 7, 14), tasks=[self.build_task(task_type) for task_type in task_types])
        return build_care_cards(digest)[0].keyboard

    def test_build_care_cards_puts_every_task_of_one_plant_on_one_card(self):
        digest = CareDigest(
            today=date(2026, 7, 14),
            tasks=[
                self.build_task(CareTaskType.WATERING, plant_id=1),
                self.build_task(CareTaskType.WATERING, plant_id=2),
                self.build_task(CareTaskType.FERTILIZING, plant_id=1),
            ],
        )

        cards = build_care_cards(digest)

        self.assertEqual(
            [(card.plant_id, card.task_types) for card in cards],
            [
                (1, frozenset({CareTaskType.WATERING, CareTaskType.FERTILIZING})),
                (2, frozenset({CareTaskType.WATERING})),
            ],
        )

    def test_build_care_cards_pairs_each_task_with_a_defer_button(self):
        keyboard = self.build_card_keyboard(CareTaskType.WATERING, CareTaskType.FERTILIZING)

        self.assertEqual(
            [[button.text for button in row] for row in keyboard.inline_keyboard],
            [["Полито", "Відкласти"], ["Підживлено", "Відкласти"]],
        )

    def test_build_care_cards_colours_the_action_green_and_leaves_the_defer_plain(self):
        keyboard = self.build_card_keyboard(CareTaskType.WATERING)

        self.assertEqual([button.style for button in keyboard.inline_keyboard[0]], ["success", None])

    def test_build_care_cards_for_a_photo_keeps_the_upload_action_behind_the_first_button(self):
        keyboard = self.build_card_keyboard(CareTaskType.PHOTO)

        self.assertEqual(
            [button.callback_data for button in keyboard.inline_keyboard[0]],
            [f"plant:photo_due:{PLANT_ID}", f"schedule:postpone:{PLANT_ID}:photo:0"],
        )


class PlantCardKeyboardTestCase(unittest.TestCase):
    def test_build_plant_card_keyboard_omits_the_button_of_a_task_already_recorded(self):
        keyboard = build_plant_card_keyboard(build_card(), recorded_task_types=frozenset({CareTaskType.WATERING}))

        self.assertNotIn(
            f"care:{PLANT_ID}:watering:0:1",
            [button.callback_data for row in keyboard.inline_keyboard for button in row],
        )

    def test_build_plant_card_keyboard_marks_its_record_buttons_as_coming_from_the_plant_card(self):
        keyboard = build_plant_card_keyboard(build_card())

        self.assertIn(
            f"care:{PLANT_ID}:watering:0:1",
            [button.callback_data for row in keyboard.inline_keyboard for button in row],
        )

    def test_find_recorded_task_types_reads_the_missing_buttons_back_from_the_keyboard(self):
        card = build_card()
        keyboard = build_plant_card_keyboard(card, recorded_task_types=frozenset({CareTaskType.WATERING}))

        recorded = find_recorded_task_types(card, keyboard)

        self.assertEqual(recorded, frozenset({CareTaskType.WATERING, CareTaskType.PHOTO}))

    def test_build_plant_card_keyboard_colours_removing_the_plant_red(self):
        keyboard = build_plant_card_keyboard(build_card())

        styles_by_text = {button.text: button.style for row in keyboard.inline_keyboard for button in row}

        self.assertEqual(styles_by_text["Прибрати"], "danger")


class ButtonTextTestCase(unittest.TestCase):
    """Emoji live in the text of a card; on a button the colour says what the emoji used to."""

    def test_every_plant_button_text_is_free_of_emoji(self):
        card = build_card()
        keyboards = [
            *(care_card.keyboard for care_card in build_care_cards(_digest_of_every_task())),
            build_force_care_keyboard(PLANT_ID, CareTaskType.FERTILIZING),
            build_plant_list_keyboard([PlantSummary(id=PLANT_ID, name="Непентес", location=None, schedules=[])]),
            build_plant_card_keyboard(card),
            build_plant_edit_keyboard(card),
            build_task_type_keyboard(card),
            build_schedule_interval_keyboard(PLANT_ID, CareTaskType.FERTILIZING),
            build_new_plant_interval_keyboard(),
            build_archive_confirmation_keyboard(PLANT_ID),
            build_archived_plant_keyboard(PLANT_ID),
            build_recorded_care_keyboard(PLANT_ID, CareTaskType.WATERING),
            build_schedule_remove_keyboard(PLANT_ID, CareTaskType.FERTILIZING),
        ]

        decorated_texts = [
            button.text
            for keyboard in keyboards
            for row in keyboard.inline_keyboard
            for button in row
            if EMOJI_PATTERN.search(button.text)
        ]

        self.assertEqual(decorated_texts, [])


def _digest_of_every_task() -> CareDigest:
    return CareDigest(
        today=date(2026, 7, 14),
        tasks=[
            DueCareTask(plant_id=PLANT_ID, plant_name="Непентес", task_type=task_type, interval_days=30, overdue_days=0)
            for task_type in CareTaskType
        ],
    )
