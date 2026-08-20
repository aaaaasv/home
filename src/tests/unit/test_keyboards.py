import unittest
from datetime import date, datetime, timezone

from src.bot.handlers.places.keyboards import build_place_item_keyboard, build_places_list_keyboard
from src.bot.handlers.plants.keyboards import (
    build_care_cards,
    build_force_care_keyboard,
    build_new_plant_interval_keyboard,
    build_new_plant_last_watered_keyboard,
    build_plant_card_keyboard,
    build_plant_edit_keyboard,
    build_plant_list_keyboard,
    build_schedule_interval_keyboard,
    build_task_type_keyboard,
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
        notes="гине від жорсткої води",
        created_at=MOMENT,
        schedules=[build_schedule(task_type) for task_type in CareTaskType],
        recent_events=[],
        latest_photo=None,
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
            build_force_care_keyboard(PLANT_ID, CareTaskType.FERTILIZING),
            build_plant_list_keyboard(summaries),
            build_plant_card_keyboard(card),
            build_plant_edit_keyboard(card),
            build_task_type_keyboard(card),
            build_schedule_interval_keyboard(PLANT_ID, CareTaskType.FERTILIZING),
            build_new_plant_interval_keyboard(),
            build_new_plant_last_watered_keyboard(),
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


class CareCardPostponeButtonTestCase(unittest.TestCase):
    def build_button_text(self, interval_days: int, task_type: CareTaskType = CareTaskType.WATERING) -> str:
        digest = CareDigest(
            today=date(2026, 7, 14),
            tasks=[
                DueCareTask(
                    plant_id=PLANT_ID,
                    plant_name="Кактус",
                    task_type=task_type,
                    interval_days=interval_days,
                    overdue_days=0,
                )
            ],
        )
        return build_care_cards(digest)[0].keyboard.inline_keyboard[1][0].text

    def test_care_card_postpone_button_declines_the_day_count(self):
        self.assertEqual(self.build_button_text(interval_days=3), "⏳ нагадати через 1 день")
        self.assertEqual(self.build_button_text(interval_days=7), "⏳ нагадати через 2 дні")
        self.assertEqual(self.build_button_text(interval_days=30), "⏳ нагадати через 10 днів")

    def test_care_card_postpone_button_caps_a_multi_year_cycle_at_two_weeks(self):
        self.assertEqual(self.build_button_text(interval_days=1095), "⏳ нагадати через 14 днів")

    def test_care_card_defer_button_for_fertilizing_offers_a_plain_skip(self):
        self.assertEqual(self.build_button_text(interval_days=30, task_type=CareTaskType.FERTILIZING), "⏭ пропустити")

    def test_care_card_defer_button_for_a_photo_offers_a_plain_skip(self):
        self.assertEqual(self.build_button_text(interval_days=30, task_type=CareTaskType.PHOTO), "⏭ пропустити")
