import unittest

from aiogram.types import InlineKeyboardMarkup

from src.bot.handlers.air_conditioner.keyboards import (
    build_air_conditioner_keyboard,
    build_air_conditioner_stop_keyboard,
)
from src.bot.handlers.chores import messages as chores_messages
from src.bot.handlers.chores.keyboards import build_chore_assignee_keyboard, build_chore_item_keyboard
from src.bot.handlers.places import messages as places_messages
from src.bot.handlers.places.keyboards import build_place_item_keyboard
from src.bot.handlers.power.keyboards import build_conservation_keyboard, build_ecoflow_keyboard
from src.bot.handlers.shopping import messages as shopping_messages
from src.bot.handlers.shopping.keyboards import build_shopping_item_keyboard
from src.modules.air_conditioner.domain import AirConditionerMode, AirConditionerState
from src.modules.chores.domain import ChoreDetails
from src.modules.family.domain import FamilyMember
from src.modules.places.domain import PlaceDetails
from src.modules.power.domain import EcoFlowState
from src.modules.shopping.constants import ShoppingHorizon
from src.modules.shopping.domain import ShoppingItemDetails
from src.tests.integration.base import FROZEN_NOW

# telegram rejects an input hint longer than this
PLACEHOLDER_MAX_LENGTH = 64


def read_buttons(markup: InlineKeyboardMarkup) -> list[tuple[str, str | None]]:
    return [(button.text, button.style) for row in markup.inline_keyboard for button in row]


def build_air_conditioner_state(is_on: bool) -> AirConditionerState:
    return AirConditionerState(
        is_on=is_on, mode=AirConditionerMode.COOL, target_temperature_celsius=24, room_temperature_celsius=26
    )


def build_ecoflow_state(ac_output_on: bool) -> EcoFlowState:
    return EcoFlowState(
        battery_percent=80.0,
        on_mains=True,
        ac_input_power=100,
        ac_output_power=0,
        ac_output_on=ac_output_on,
        usb_output_on=False,
        dc_output_on=False,
        remaining_minutes=None,
        charge_limit_max=None,
        backup_reserve_percent=None,
        cell_temperature_celsius=None,
        as_of=FROZEN_NOW,
    )


class ShoppingButtonStylesTestCase(unittest.TestCase):
    def build_item(self, horizon: ShoppingHorizon, tracked: bool) -> ShoppingItemDetails:
        return ShoppingItemDetails(
            id=7,
            name="Пилосос",
            horizon=horizon,
            added_by_display_name="Богдан",
            current_price=21999 if tracked else None,
            initial_price=21999 if tracked else None,
        )

    def test_build_shopping_item_keyboard_paints_buy_green_and_remove_red_without_emoji(self):
        markup = build_shopping_item_keyboard(self.build_item(ShoppingHorizon.LATER, tracked=False))

        self.assertEqual(
            read_buttons(markup),
            [
                ("Купили", "success"),
                ("Перейменувати", None),
                ("У «Зараз»", None),
                ("Стежити", None),
                ("Фото", None),
                ("Опис", None),
                ("Прибрати", "danger"),
                ("← Назад", None),
            ],
        )

    def test_build_shopping_item_keyboard_for_a_tracked_needed_item_drops_promote_and_track(self):
        markup = build_shopping_item_keyboard(self.build_item(ShoppingHorizon.NOW, tracked=True))

        self.assertEqual(
            [text for text, _ in read_buttons(markup)],
            ["Купили", "Перейменувати", "Фото", "Опис", "Прибрати", "← Назад"],
        )


class ChoresButtonStylesTestCase(unittest.TestCase):
    def test_build_chore_item_keyboard_paints_done_green_and_remove_red_without_emoji(self):
        chore = ChoreDetails(
            id=3,
            name="Забрати посилку",
            due_on=None,
            added_by_display_name="Марта",
            assignee_telegram_user_id=None,
            assignee_display_name=None,
            completed_at=None,
            completed_by_display_name=None,
        )

        markup = build_chore_item_keyboard(chore)

        self.assertEqual(
            read_buttons(markup),
            [
                ("Зроблено", "success"),
                ("Дата", None),
                ("Чия", None),
                ("Перейменувати", None),
                ("Прибрати", "danger"),
                ("← Назад", None),
            ],
        )

    def test_build_chore_assignee_keyboard_offers_nobody_without_emoji_or_colour(self):
        member = FamilyMember(telegram_user_id=2, display_name="Марта")

        markup = build_chore_assignee_keyboard(3, [member])

        self.assertEqual(read_buttons(markup), [("Марта", None), ("Нічия", None), ("← Назад", None)])


class PlacesButtonStylesTestCase(unittest.TestCase):
    def test_build_place_item_keyboard_paints_visited_green_and_remove_red_without_emoji(self):
        place = PlaceDetails(
            id=5,
            name="Кафе",
            link=None,
            address=None,
            note=None,
            setting=None,
            added_by_display_name="Марта",
            visited_at=None,
            visited_by_display_name=None,
        )

        markup = build_place_item_keyboard(place)

        self.assertEqual(
            read_buttons(markup),
            [("Були", "success"), ("Перейменувати", None), ("Прибрати", "danger"), ("← Назад", None)],
        )


class AirConditionerButtonStylesTestCase(unittest.TestCase):
    def test_build_air_conditioner_keyboard_on_a_running_unit_paints_turn_off_red(self):
        markup = build_air_conditioner_keyboard(build_air_conditioner_state(is_on=True))

        self.assertEqual(read_buttons(markup)[0], ("Вимкнути", "danger"))

    def test_build_air_conditioner_keyboard_on_a_stopped_unit_leaves_turn_on_plain(self):
        markup = build_air_conditioner_keyboard(build_air_conditioner_state(is_on=False))

        self.assertEqual(read_buttons(markup)[0], ("Увімкнути", None))

    def test_build_air_conditioner_keyboard_paints_nothing_but_turn_off(self):
        markup = build_air_conditioner_keyboard(build_air_conditioner_state(is_on=True))

        self.assertEqual([style for _, style in read_buttons(markup)[1:]], [None] * 10)

    def test_build_air_conditioner_stop_keyboard_paints_turn_off_red(self):
        markup = build_air_conditioner_stop_keyboard()

        self.assertEqual(read_buttons(markup), [("Вимкнути", "danger")])


class PowerButtonStylesTestCase(unittest.TestCase):
    def test_build_ecoflow_keyboard_with_the_outlets_off_paints_turning_them_on_blue(self):
        markup = build_ecoflow_keyboard(build_ecoflow_state(ac_output_on=False))

        self.assertEqual(
            read_buttons(markup),
            [
                ("Розетки увімкнути", "primary"),
                ("USB увімкнути", None),
                ("DC 12В увімкнути", None),
                ("Оновити", None),
            ],
        )

    def test_build_ecoflow_keyboard_with_the_outlets_on_leaves_turning_them_off_plain(self):
        markup = build_ecoflow_keyboard(build_ecoflow_state(ac_output_on=True))

        self.assertEqual(read_buttons(markup)[0], ("Розетки вимкнути", None))

    def test_build_conservation_keyboard_carries_no_emoji_and_no_colour(self):
        self.assertEqual(
            read_buttons(build_conservation_keyboard(is_conserved=False)), [("Позначити на зберігання", None)]
        )
        self.assertEqual(
            read_buttons(build_conservation_keyboard(is_conserved=True)), [("Позначити у користуванні", None)]
        )


class ForceReplyPlaceholdersTestCase(unittest.TestCase):
    def collect_placeholders(self, module) -> list[str]:
        return [value for name, value in vars(module).items() if name.endswith("PLACEHOLDER")]

    def test_every_placeholder_fits_telegrams_limit_for_an_input_hint(self):
        placeholders = [
            *self.collect_placeholders(shopping_messages),
            *self.collect_placeholders(chores_messages),
            *self.collect_placeholders(places_messages),
        ]

        too_long = [placeholder for placeholder in placeholders if not 0 < len(placeholder) <= PLACEHOLDER_MAX_LENGTH]

        self.assertEqual(too_long, [])
        self.assertEqual(len(placeholders), 8)
