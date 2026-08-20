import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.bot.formatting import exceeds_caption_limit, format_day, format_due, pluralize_days, shorten_for_button
from src.bot.handlers.chores.formatting import render_chore_deadline_card, render_chores_list
from src.bot.handlers.places.formatting import render_places_list
from src.bot.handlers.plants.formatting import (
    render_care_card_caption,
    render_plant_card,
    render_plant_comfort_restored,
    render_plant_discomfort_card,
    render_plant_photo_review,
    render_schedule_remove_confirm,
)
from src.bot.handlers.shopping.formatting import render_price_drop_alert, render_shopping_list
from src.bot.handlers.system.formatting import render_pi_health
from src.bot.handlers.transit.formatting import render_transit_card
from src.bot.handlers.weather.formatting import render_climate_digest
from src.common.constants import (
    CareTaskType,
    ClimateComfortTransition,
    ClimateDimension,
    ClimateStatus,
    PlantPhotoReviewStatus,
)
from src.common.household_calendar import HouseholdCalendar
from src.modules.chores.domain import ChoreDetails, ChoreReminder, ChoresList
from src.modules.places.domain import PlaceDetails, PlacesList
from src.modules.plant_care.domain import (
    CareEventDetails,
    CareScheduleDetails,
    ClimateProblem,
    DueCareTask,
    PlantCard,
    PlantComfortChange,
    PlantPhotoReview,
)
from src.modules.plant_care.services.room_climate_sensor import RoomClimate
from src.modules.shopping.constants import ShoppingHorizon
from src.modules.shopping.domain import PriceDropAnnouncement, ShoppingItemDetails, ShoppingList
from src.modules.system_health.domain import PiHealthReading
from src.modules.transit.domain import RouteArrival, RouteVehicleKind, TransitReport, TransitReportStatus, WatchedRoute
from src.modules.weather.domain import PollenReading, PollenSpecies, RainWindow, VentilationEffect, WeatherReport

MOMENT = datetime(2026, 7, 16, 9, 0, tzinfo=timezone.utc)


class RenderPlantCardTestCase(unittest.TestCase):
    def build_card(self, with_history: bool) -> PlantCard:
        events = []
        if with_history:
            events = [
                CareEventDetails(
                    task_type=CareTaskType.WATERING, performed_at=MOMENT, performed_by_display_name="Богдан", note=None
                )
            ]
        return PlantCard(
            id=1,
            name="Кактус",
            species=None,
            location=None,
            notes=None,
            created_at=MOMENT,
            schedules=[],
            recent_events=events,
            latest_photo=None,
            photo_count=0,
        )

    def test_render_plant_card_collapses_the_history_into_an_expandable_blockquote(self):
        rendered = render_plant_card(
            self.build_card(with_history=True), HouseholdCalendar(timezone=ZoneInfo("Europe/Kyiv"))
        )

        self.assertIn("<blockquote expandable><b>Останні дії</b>", rendered)
        self.assertIn("Богдан", rendered)

    def test_render_plant_card_without_history_has_no_blockquote(self):
        rendered = render_plant_card(
            self.build_card(with_history=False), HouseholdCalendar(timezone=ZoneInfo("Europe/Kyiv"))
        )

        self.assertNotIn("blockquote", rendered)

    def test_render_plant_card_gives_each_schedule_instruction_its_own_expandable_block(self):
        card = self.build_card(with_history=False).model_copy(
            update={
                "schedules": [
                    CareScheduleDetails(
                        task_type=CareTaskType.WATERING,
                        interval_days=4,
                        next_due_on=date(2026, 7, 20),
                        last_performed_at=None,
                        days_until_due=4,
                        instructions="Промацай ґрунт на 3 см.",
                    ),
                    CareScheduleDetails(
                        task_type=CareTaskType.FERTILIZING,
                        interval_days=14,
                        next_due_on=date(2026, 7, 30),
                        last_performed_at=None,
                        days_until_due=14,
                        instructions="½ — 1 мл на 0.5 л.",
                    ),
                ]
            }
        )

        rendered = render_plant_card(card, HouseholdCalendar(timezone=ZoneInfo("Europe/Kyiv")))

        self.assertIn("<blockquote expandable>Промацай ґрунт на 3 см.</blockquote>", rendered)
        self.assertIn("<blockquote expandable>½ — 1 мл на 0.5 л.</blockquote>", rendered)
        self.assertEqual(rendered.count("<blockquote expandable>"), 2)

    def test_render_plant_card_omits_the_block_for_a_schedule_without_instructions(self):
        card = self.build_card(with_history=False).model_copy(
            update={
                "schedules": [
                    CareScheduleDetails(
                        task_type=CareTaskType.WATERING,
                        interval_days=4,
                        next_due_on=date(2026, 7, 20),
                        last_performed_at=None,
                        days_until_due=4,
                        instructions=None,
                    )
                ]
            }
        )

        rendered = render_plant_card(card, HouseholdCalendar(timezone=ZoneInfo("Europe/Kyiv")))

        self.assertNotIn("blockquote", rendered)


class RenderShoppingListTestCase(unittest.TestCase):
    def item(self, name: str, horizon: ShoppingHorizon) -> ShoppingItemDetails:
        return ShoppingItemDetails(id=1, name=name, horizon=horizon, added_by_display_name="Марта")

    def test_render_shopping_list_collapses_the_someday_section_into_an_expandable_blockquote(self):
        shopping_list = ShoppingList(
            needed_now=[self.item("олія", ShoppingHorizon.NOW)],
            wanted_later=[self.item("пилосос", ShoppingHorizon.LATER)],
        )

        rendered = render_shopping_list(shopping_list)

        self.assertIn("<blockquote expandable><b>Колись</b>\n· пилосос</blockquote>", rendered)

    def test_render_shopping_list_without_a_someday_section_has_no_blockquote(self):
        shopping_list = ShoppingList(needed_now=[self.item("олія", ShoppingHorizon.NOW)], wanted_later=[])

        rendered = render_shopping_list(shopping_list)

        self.assertNotIn("blockquote", rendered)


class RenderCareCardCaptionTestCase(unittest.TestCase):
    def build_task(self, overdue_days: int = 0, instructions: str | None = None) -> DueCareTask:
        return DueCareTask(
            plant_id=1,
            plant_name="Кактус",
            task_type=CareTaskType.WATERING,
            interval_days=3,
            overdue_days=overdue_days,
            instructions=instructions,
        )

    def test_render_care_card_caption_heads_with_the_plant_and_lists_the_task(self):
        caption = render_care_card_caption(self.build_task())

        self.assertEqual(caption, "🪴 <b>Кактус</b>\n💧 полив")

    def test_render_care_card_caption_marks_an_overdue_task(self):
        caption = render_care_card_caption(self.build_task(overdue_days=2))

        self.assertEqual(caption, "🔴 <b>Кактус</b>\n💧 полив <i>(прострочено 2 дні)</i>")

    def test_render_care_card_caption_puts_instructions_in_an_expandable_block(self):
        caption = render_care_card_caption(self.build_task(instructions="Поливайте рясно, але рідко."))

        self.assertIn("<blockquote expandable>Поливайте рясно, але рідко.</blockquote>", caption)


class RenderClimateDigestTestCase(unittest.TestCase):
    def build_report(self, **overrides) -> WeatherReport:
        defaults = dict(
            temperature_celsius=28.0,
            apparent_temperature_celsius=28.5,
            relative_humidity_percent=55.0,
            temperature_max_celsius=31.0,
            temperature_min_celsius=18.0,
            temperature_evening_celsius=None,
            uv_index_max=None,
            is_thunderstorm_expected=False,
            wind_speed_meters_per_second=3.2,
            precipitation_probability_percent=10,
            rain_window=None,
            european_air_quality_index=39,
            pm2_5_micrograms=8.8,
            pollen=[],
        )
        defaults.update(overrides)
        return WeatherReport(**defaults)

    def test_render_climate_digest_shows_indoor_outdoor_rain_and_air_quality(self):
        indoor = RoomClimate(temperature_celsius=28.5, relative_humidity_percent=33.0)

        rendered = render_climate_digest(indoor, self.build_report(precipitation_probability_percent=45))

        self.assertIn("🏠 вдома: 28° · 33%", rendered)
        self.assertIn("🌍 надворі: 28°, удень до 31°", rendered)
        self.assertIn("☔ дощ: 45%", rendered)
        self.assertIn("🌫 повітря: добре (AQI 39)", rendered)

    def test_render_climate_digest_names_the_evening_temperature_when_it_is_still_ahead(self):
        rendered = render_climate_digest(None, self.build_report(temperature_evening_celsius=21.4))

        self.assertIn("🌍 надворі: 28°, удень до 31°, ввечері 21°", rendered)

    def test_render_climate_digest_appends_the_as_of_time_when_given(self):
        moment = datetime(2026, 7, 27, 14, 35, tzinfo=timezone.utc)

        rendered = render_climate_digest(None, self.build_report(), generated_at=moment)

        self.assertTrue(rendered.endswith("\n\n<i>станом на 14:35</i>"))

    def test_render_climate_digest_omits_the_as_of_time_by_default(self):
        rendered = render_climate_digest(None, self.build_report())

        self.assertNotIn("станом на", rendered)

    def test_render_climate_digest_warns_about_a_thunderstorm(self):
        rendered = render_climate_digest(None, self.build_report(is_thunderstorm_expected=True))

        self.assertIn("⛈️ можлива гроза", rendered)

    def test_render_climate_digest_warns_about_frost_ahead(self):
        rendered = render_climate_digest(None, self.build_report(temperature_min_celsius=-2.0))

        self.assertIn("❄️ вночі до -2° — заносьте рослини з балкона", rendered)

    def test_render_climate_digest_stays_silent_about_frost_above_the_threshold(self):
        rendered = render_climate_digest(None, self.build_report(temperature_min_celsius=1.6))

        self.assertNotIn("вночі", rendered)

    def test_render_climate_digest_warns_about_high_uv(self):
        rendered = render_climate_digest(None, self.build_report(uv_index_max=6.35))

        self.assertIn("☀️ УФ високий — крем і кепка", rendered)

    def test_render_climate_digest_stays_silent_about_low_uv(self):
        rendered = render_climate_digest(None, self.build_report(uv_index_max=5.9))

        self.assertNotIn("УФ", rendered)

    def test_render_climate_digest_shows_the_ventilation_fact_when_given(self):
        rendered = render_climate_digest(None, self.build_report(), VentilationEffect.DRIER)

        self.assertIn("🪟 надворі сухіше", rendered)

    def test_render_climate_digest_without_ventilation_fact_has_no_window_line(self):
        rendered = render_climate_digest(None, self.build_report())

        self.assertNotIn("🪟", rendered)

    def test_render_climate_digest_on_a_calm_day_has_no_wind_line(self):
        rendered = render_climate_digest(None, self.build_report(wind_speed_meters_per_second=7.9))

        self.assertNotIn("💨", rendered)

    def test_render_climate_digest_grades_the_wind_by_band(self):
        bands = {
            8.0: "вітряно",
            10.8: "вітряно",
            12.0: "сильний вітер",
            17.2: "сильний вітер",
            17.3: "дуже сильний вітер",
        }

        rendered = {
            speed: render_climate_digest(None, self.build_report(wind_speed_meters_per_second=speed)) for speed in bands
        }

        for speed, label in bands.items():
            self.assertIn(f"💨 {label}", rendered[speed])

    def test_render_climate_digest_without_a_wind_reading_has_no_wind_line(self):
        rendered = render_climate_digest(None, self.build_report(wind_speed_meters_per_second=None))

        self.assertNotIn("💨", rendered)

    def test_render_climate_digest_shows_the_feels_like_when_it_differs_enough(self):
        report = self.build_report(temperature_celsius=8.0, apparent_temperature_celsius=3.0)

        rendered = render_climate_digest(None, report)

        self.assertIn("🌍 надворі: 8° (відчувається як 3°), удень до 31°", rendered)

    def test_render_climate_digest_hides_the_feels_like_when_it_is_close(self):
        report = self.build_report(temperature_celsius=23.0, apparent_temperature_celsius=25.9)

        rendered = render_climate_digest(None, report)

        self.assertIn("🌍 надворі: 23°, удень до 31°", rendered)
        self.assertNotIn("відчувається", rendered)

    def test_render_climate_digest_without_a_feels_like_reading_shows_the_plain_line(self):
        report = self.build_report(apparent_temperature_celsius=None)

        rendered = render_climate_digest(None, report)

        self.assertIn("🌍 надворі: 28°, удень до 31°", rendered)

    def test_render_climate_digest_with_a_rain_window_names_the_hours(self):
        report = self.build_report(
            precipitation_probability_percent=63, rain_window=RainWindow(start_hour=8, end_hour=9)
        )

        rendered = render_climate_digest(None, report)

        self.assertIn("☔ дощ: 63% — найімовірніше 08:00–09:00", rendered)

    def test_render_climate_digest_with_a_single_hour_rain_window_names_that_hour(self):
        report = self.build_report(
            precipitation_probability_percent=80, rain_window=RainWindow(start_hour=17, end_hour=17)
        )

        rendered = render_climate_digest(None, report)

        self.assertIn("☔ дощ: 80% — найімовірніше о 17:00", rendered)

    def test_render_climate_digest_without_a_rain_window_shows_the_bare_probability(self):
        rendered = render_climate_digest(None, self.build_report(precipitation_probability_percent=45))

        self.assertIn("☔ дощ: 45%", rendered)
        self.assertNotIn("найімовірніше", rendered)

    def test_render_climate_digest_stays_silent_about_an_unlikely_rain(self):
        rendered = render_climate_digest(None, self.build_report(precipitation_probability_percent=5))

        self.assertNotIn("☔", rendered)

    def test_render_climate_digest_lists_pollen_above_the_threshold_with_levels(self):
        report = self.build_report(
            pollen=[
                PollenReading(species=PollenSpecies.RAGWEED, grains_per_cubic_meter=15.0),
                PollenReading(species=PollenSpecies.GRASS, grains_per_cubic_meter=80.0),
            ]
        )

        rendered = render_climate_digest(None, report)

        self.assertIn("🌾 пилок: амброзія помірно, трава високо", rendered)

    def test_render_climate_digest_hides_pollen_below_the_threshold(self):
        report = self.build_report(pollen=[PollenReading(species=PollenSpecies.GRASS, grains_per_cubic_meter=5.0)])

        rendered = render_climate_digest(None, report)

        self.assertNotIn("пилок", rendered)

    def test_render_climate_digest_without_outdoor_says_the_forecast_is_unavailable(self):
        indoor = RoomClimate(temperature_celsius=28.5, relative_humidity_percent=33.0)

        rendered = render_climate_digest(indoor, None)

        self.assertEqual(rendered, "🌤 <b>Погода</b>\n\n🏠 вдома: 28° · 33%\n🌤 Погода зараз недоступна.")

    def test_render_climate_digest_without_indoor_shows_only_the_outdoor_line(self):
        rendered = render_climate_digest(None, self.build_report())

        self.assertNotIn("вдома", rendered)
        self.assertIn("🌍 надворі", rendered)


class RenderPiHealthTestCase(unittest.TestCase):
    def build_reading(self, is_undervoltage: bool = False) -> PiHealthReading:
        return PiHealthReading(temperature_celsius=58.9, is_undervoltage=is_undervoltage, disk_used_percent=32.9)

    def test_render_pi_health_shows_temperature_power_and_disk(self):
        rendered = render_pi_health(self.build_reading())

        self.assertEqual(rendered, "🩺 <b>Raspberry Pi</b>\n🌡 59°\n⚡ живлення в нормі\n💾 диск: 33%")

    def test_render_pi_health_flags_undervoltage(self):
        rendered = render_pi_health(self.build_reading(is_undervoltage=True))

        self.assertIn("⚡ просідає живлення", rendered)


class ShortenForButtonTestCase(unittest.TestCase):
    def test_shorten_for_button_of_a_short_value_returns_it_unchanged(self):
        self.assertEqual(shorten_for_button("спальня"), "спальня")

    def test_shorten_for_button_of_a_long_value_truncates_it_with_an_ellipsis(self):
        self.assertEqual(shorten_for_button("Nepenthes hybrid (×ventrata)"), "Nepenthes hybrid (×vent…")

    def test_shorten_for_button_of_an_empty_field_returns_a_dash(self):
        self.assertEqual(shorten_for_button(None), "—")


class PluralizeDaysTestCase(unittest.TestCase):
    def test_pluralize_days_returns_the_ukrainian_plural_forms(self):
        self.assertEqual(pluralize_days(1), "1 день")
        self.assertEqual(pluralize_days(2), "2 дні")
        self.assertEqual(pluralize_days(4), "4 дні")
        self.assertEqual(pluralize_days(5), "5 днів")
        self.assertEqual(pluralize_days(11), "11 днів")
        self.assertEqual(pluralize_days(14), "14 днів")
        self.assertEqual(pluralize_days(21), "21 день")
        self.assertEqual(pluralize_days(22), "22 дні")
        self.assertEqual(pluralize_days(25), "25 днів")


class FormatDueTestCase(unittest.TestCase):
    def test_format_due_describes_the_days_left(self):
        self.assertEqual(format_due(-3), "прострочено 3 дні")
        self.assertEqual(format_due(-1), "прострочено 1 день")
        self.assertEqual(format_due(0), "сьогодні")
        self.assertEqual(format_due(1), "завтра")
        self.assertEqual(format_due(5), "через 5 днів")


class FormatDayTestCase(unittest.TestCase):
    def test_format_day_within_the_current_year_omits_the_year(self):
        self.assertEqual(format_day(date(2026, 7, 18), today=date(2026, 7, 12)), "18 липня")

    def test_format_day_in_another_year_includes_the_year(self):
        self.assertEqual(format_day(date(2027, 1, 3), today=date(2026, 7, 12)), "3 січня 2027")


class RenderPlantPhotoReviewTestCase(unittest.TestCase):
    def test_render_plant_photo_review_with_a_change_and_an_action_labels_both(self):
        review = PlantPhotoReview(
            status=PlantPhotoReviewStatus.PROBLEM,
            summary="Нижнє листя жовтіє.",
            change="За місяць пожовкли три нижні листки.",
            action="Промацай ґрунт на 3 см — якщо вологий, пропусти полив.",
        )

        rendered = render_plant_photo_review(review)

        self.assertEqual(
            rendered,
            "⚠️ Нижнє листя жовтіє.\n\n"
            "<i>Зміни:</i> За місяць пожовкли три нижні листки.\n"
            "<i>Що зробити:</i> Промацай ґрунт на 3 см — якщо вологий, пропусти полив.",
        )

    def test_render_plant_photo_review_without_a_change_or_an_action_is_a_single_line(self):
        review = PlantPhotoReview(
            status=PlantPhotoReviewStatus.OK, summary="Виглядає здоровою.", change=None, action=None
        )

        rendered = render_plant_photo_review(review)

        self.assertEqual(rendered, "✅ Виглядає здоровою.")


class RenderScheduleRemoveConfirmTestCase(unittest.TestCase):
    def build_schedule(self, instructions: str | None) -> CareScheduleDetails:
        return CareScheduleDetails(
            task_type=CareTaskType.FERTILIZING,
            interval_days=30,
            next_due_on=date(2026, 7, 20),
            last_performed_at=None,
            days_until_due=6,
            instructions=instructions,
        )

    def test_render_schedule_remove_confirm_warns_that_the_instruction_goes_too(self):
        rendered = render_schedule_remove_confirm("Кактус", self.build_schedule("Розводь удвічі слабше."))

        self.assertEqual(
            rendered,
            "Прибрати добриво у «Кактус»?\n\n⚠️ Інструкція до цього догляду теж зникне.",
        )

    def test_render_schedule_remove_confirm_without_an_instruction_only_asks(self):
        rendered = render_schedule_remove_confirm("Кактус", self.build_schedule(None))

        self.assertEqual(rendered, "Прибрати добриво у «Кактус»?")


class RenderTrackedShoppingListTestCase(unittest.TestCase):
    def tracked(self, current: int, initial: int) -> ShoppingItemDetails:
        return ShoppingItemDetails(
            id=1,
            name="Dyson V15",
            horizon=ShoppingHorizon.LATER,
            added_by_display_name="Богдан",
            current_price=current,
            initial_price=initial,
        )

    def test_render_shopping_list_shows_a_down_arrow_when_a_tracked_item_got_cheaper(self):
        shopping_list = ShoppingList(needed_now=[], wanted_later=[self.tracked(current=19500, initial=21999)])

        rendered = render_shopping_list(shopping_list)

        self.assertIn("🔖 Dyson V15 — 19 500 ₴ ↓", rendered)

    def test_render_shopping_list_shows_no_arrow_when_a_tracked_item_is_unchanged(self):
        shopping_list = ShoppingList(needed_now=[], wanted_later=[self.tracked(current=21999, initial=21999)])

        rendered = render_shopping_list(shopping_list)

        self.assertIn("🔖 Dyson V15 — 21 999 ₴", rendered)
        self.assertNotIn("↓", rendered)
        self.assertNotIn("↑", rendered)

    def test_render_price_drop_alert_strikes_the_old_low(self):
        announcement = PriceDropAnnouncement(
            name="Пилосос Dyson",
            hotline_url="https://hotline.ua/ua/x/dyson/",
            previous_low=21999,
            new_price=19500,
        )

        rendered = render_price_drop_alert(announcement)

        self.assertEqual(
            rendered,
            "📉 <b>Пилосос Dyson</b> подешевшав\n19 500 ₴ <s>21 999 ₴</s>\nhttps://hotline.ua/ua/x/dyson/",
        )

    def test_render_price_drop_alert_names_the_reputable_shop_and_links_straight_to_it(self):
        announcement = PriceDropAnnouncement(
            name="Пилосос Dyson",
            hotline_url="https://hotline.ua/ua/x/dyson/",
            previous_low=21999,
            new_price=19500,
            shop="Rozetka",
            rating=96,
            buy_link="https://hotline.ua/go/price/555/",
        )

        rendered = render_price_drop_alert(announcement)

        self.assertEqual(
            rendered.split("\n")[-1],
            '<a href="https://hotline.ua/go/price/555/">🏬 Rozetka · рейтинг 96</a>',
        )

    def test_render_price_drop_alert_falls_back_to_the_hotline_page_when_the_shop_has_no_buy_link(self):
        announcement = PriceDropAnnouncement(
            name="Пилосос Dyson",
            hotline_url="https://hotline.ua/ua/x/dyson/",
            previous_low=21999,
            new_price=19500,
            shop="Rozetka",
            rating=None,
        )

        rendered = render_price_drop_alert(announcement)

        self.assertEqual(
            rendered.split("\n")[-1],
            '<a href="https://hotline.ua/ua/x/dyson/">🏬 Rozetka</a>',
        )


class RenderPlacesListTestCase(unittest.TestCase):
    def place(self, name, link=None, visited_at=None, added="Марта", visited_by=None) -> PlaceDetails:
        return PlaceDetails(
            id=1,
            name=name,
            link=link,
            address=None,
            note=None,
            setting=None,
            added_by_display_name=added,
            visited_at=visited_at,
            visited_by_display_name=visited_by,
        )

    def test_render_places_list_links_a_place_that_has_a_map_url(self):
        places = PlacesList(to_visit=[self.place("Кафе", link="https://maps.app/x")], visited=[])

        rendered = render_places_list(places)

        self.assertIn('📍 <a href="https://maps.app/x">Кафе</a> · Марта', rendered)

    def test_render_places_list_collapses_the_visited_history_into_an_expandable_block(self):
        places = PlacesList(
            to_visit=[self.place("Набережна")],
            visited=[self.place("Кафе", visited_at=MOMENT, visited_by="Богдан")],
        )

        rendered = render_places_list(places)

        self.assertIn("📍 Набережна · Марта", rendered)
        self.assertIn("<blockquote expandable><b>Були</b>\n✓ Кафе · Богдан</blockquote>", rendered)

    def test_render_places_list_when_empty_invites_a_first_place(self):
        rendered = render_places_list(PlacesList(to_visit=[], visited=[]))

        self.assertEqual(rendered, "📍 Список порожній. Напиши, куди хочеться сходити — просто текстом.")


class RenderPlantDiscomfortCardTestCase(unittest.TestCase):
    def build_change(self, problems: list[ClimateProblem]) -> PlantComfortChange:
        return PlantComfortChange(
            plant_id=1,
            plant_name="Фікус",
            transition=ClimateComfortTransition.BECAME_UNCOMFORTABLE,
            problems=problems,
        )

    def test_render_plant_discomfort_card_rounds_a_low_reading_down_away_from_the_range(self):
        change = self.build_change(
            [
                ClimateProblem(
                    dimension=ClimateDimension.HUMIDITY,
                    status=ClimateStatus.TOO_LOW,
                    value=32.8,
                    ideal_min=50.0,
                    ideal_max=70.0,
                )
            ]
        )

        rendered = render_plant_discomfort_card(change)

        self.assertEqual(rendered, "💧 <b>Фікус</b> — сухо: 32%, треба 50–70%")

    def test_render_plant_discomfort_card_rounds_a_high_reading_up_away_from_the_range(self):
        change = self.build_change(
            [
                ClimateProblem(
                    dimension=ClimateDimension.TEMPERATURE,
                    status=ClimateStatus.TOO_HIGH,
                    value=29.1,
                    ideal_min=18.0,
                    ideal_max=27.0,
                )
            ]
        )

        rendered = render_plant_discomfort_card(change)

        self.assertEqual(rendered, "🔥 <b>Фікус</b> — жарко: 30°, треба 18–27°")

    def test_render_plant_discomfort_card_lists_one_line_per_problem(self):
        change = self.build_change(
            [
                ClimateProblem(
                    dimension=ClimateDimension.TEMPERATURE,
                    status=ClimateStatus.TOO_HIGH,
                    value=30.0,
                    ideal_min=18.0,
                    ideal_max=27.0,
                ),
                ClimateProblem(
                    dimension=ClimateDimension.HUMIDITY,
                    status=ClimateStatus.TOO_LOW,
                    value=30.0,
                    ideal_min=50.0,
                    ideal_max=70.0,
                ),
            ]
        )

        rendered = render_plant_discomfort_card(change)

        self.assertEqual(
            rendered,
            "🔥 <b>Фікус</b> — жарко: 30°, треба 18–27°\n💧 <b>Фікус</b> — сухо: 30%, треба 50–70%",
        )

    def test_render_plant_comfort_restored_names_the_plant(self):
        rendered = render_plant_comfort_restored("Фікус")

        self.assertEqual(rendered, "✅ <b>Фікус</b> — знову комфортно")

    def test_render_plant_comfort_restored_escapes_a_name_with_markup(self):
        rendered = render_plant_comfort_restored("Фікус <3")

        self.assertEqual(rendered, "✅ <b>Фікус &lt;3</b> — знову комфортно")


class RenderChoresTestCase(unittest.TestCase):
    TODAY = date(2026, 7, 28)

    def chore(self, name: str, due_on: date | None, assignee: str | None = None) -> ChoreDetails:
        return ChoreDetails(
            id=1,
            name=name,
            due_on=due_on,
            added_by_display_name="Богдан",
            assignee_telegram_user_id=1 if assignee else None,
            assignee_display_name=assignee,
            completed_at=None,
            completed_by_display_name=None,
        )

    def test_render_chore_deadline_card_marks_a_future_deadline_with_a_calendar(self):
        card = render_chore_deadline_card(ChoreReminder(chore_id=1, name="негативи", days_until_due=1))

        self.assertEqual(card, "📅 <b>негативи</b> — завтра")

    def test_render_chore_deadline_card_marks_an_overdue_deadline_red(self):
        card = render_chore_deadline_card(ChoreReminder(chore_id=1, name="негативи", days_until_due=-2))

        self.assertEqual(card, "🔴 <b>негативи</b> — прострочено 2 дні")

    def test_render_chores_list_when_empty_invites_a_first_chore(self):
        rendered = render_chores_list(ChoresList(dated=[], someday=[]), self.TODAY)

        self.assertEqual(rendered, "📋 Порожньо. Напиши, що треба зробити — просто текстом.")

    def test_render_chores_list_says_nothing_is_burning_when_no_deadline_is_due(self):
        chores = ChoresList(dated=[self.chore("негативи", self.TODAY + timedelta(days=3))], someday=[])

        rendered = render_chores_list(chores, self.TODAY)

        self.assertIn("нічого не горить ✨", rendered)
        self.assertIn("📌 негативи · 31 липня", rendered)

    def test_render_chores_list_counts_the_burning_deadlines_and_marks_them_red(self):
        chores = ChoresList(
            dated=[self.chore("вчора", self.TODAY - timedelta(days=1)), self.chore("сьогодні", self.TODAY)],
            someday=[],
        )

        rendered = render_chores_list(chores, self.TODAY)

        self.assertIn("🔥 горить: 2", rendered)
        self.assertIn("🔴 вчора · 27 липня", rendered)
        self.assertIn("🔴 сьогодні · 28 липня", rendered)

    def test_render_chores_list_collapses_the_someday_pile_into_a_blockquote(self):
        chores = ChoresList(dated=[], someday=[self.chore("почистити ноутбук", None)])

        rendered = render_chores_list(chores, self.TODAY)

        self.assertIn("<blockquote expandable><b>Колись</b>\n· почистити ноутбук</blockquote>", rendered)


class RenderChoreAssigneeTestCase(unittest.TestCase):
    def test_render_chore_deadline_card_mentions_the_assignee(self):
        reminder = ChoreReminder(
            chore_id=1,
            name="забрати посилку",
            days_until_due=1,
            assignee_telegram_user_id=555,
            assignee_display_name="Марта",
        )

        card = render_chore_deadline_card(reminder)

        self.assertEqual(card, '📅 <b>забрати посилку</b> — завтра · 👤 <a href="tg://user?id=555">Марта</a>')

    def test_render_chore_deadline_card_without_an_assignee_has_no_mention(self):
        reminder = ChoreReminder(chore_id=1, name="забрати посилку", days_until_due=1)

        card = render_chore_deadline_card(reminder)

        self.assertNotIn("tg://user", card)

    def test_render_chores_list_shows_the_owner_as_plain_text_never_a_mention(self):
        chore = ChoreDetails(
            id=1,
            name="забрати посилку",
            due_on=date(2026, 7, 29),
            added_by_display_name="Богдан",
            assignee_telegram_user_id=555,
            assignee_display_name="Марта",
            completed_at=None,
            completed_by_display_name=None,
        )

        rendered = render_chores_list(ChoresList(dated=[chore], someday=[]), date(2026, 7, 28))

        self.assertIn("👤 Марта", rendered)
        # the board edits itself silently — a tg:// mention there would re-ping the person on every refresh
        self.assertNotIn("tg://user", rendered)


class RenderTransitCardTestCase(unittest.TestCase):
    def build_arrivals_report(self) -> TransitReport:
        return TransitReport(
            status=TransitReportStatus.ARRIVALS,
            arrivals=[
                RouteArrival(
                    route=WatchedRoute(route_id="2_30", short_name="3", vehicle_kind=RouteVehicleKind.TROLLEYBUS),
                    eta_minutes=4,
                    distance_meters=1100.0,
                ),
                RouteArrival(
                    route=WatchedRoute(route_id="3_127", short_name="69", vehicle_kind=RouteVehicleKind.BUS),
                    eta_minutes=9,
                    distance_meters=2500.0,
                ),
                RouteArrival(
                    route=WatchedRoute(route_id="2_842", short_name="9К", vehicle_kind=RouteVehicleKind.TROLLEYBUS),
                    eta_minutes=None,
                    distance_meters=None,
                ),
            ],
        )

    def test_render_transit_card_names_the_nearest_route_with_distance_then_the_rest_as_bare_eta(self):
        card = render_transit_card(self.build_arrivals_report(), MOMENT, is_live=True)

        self.assertEqual(
            card,
            "найближчий: 🚎 3 за ~4 хв (~1.1 км) · 🚌 69 ~9 хв · 🚎 9К поки не видно\n\n"
            "<i>оновлюється · станом на 09:00</i>",
        )

    def test_render_transit_card_during_an_air_raid_shows_the_jamming_notice(self):
        report = TransitReport(status=TransitReportStatus.AIR_RAID)

        card = render_transit_card(report, MOMENT, is_live=True)

        self.assertEqual(
            card,
            "🚨 тривога — GPS заглушено, даних нема\n\n<i>оновлюється · станом на 09:00</i>",
        )

    def test_render_transit_card_when_the_feed_is_unavailable_shows_the_tracking_notice(self):
        report = TransitReport(status=TransitReportStatus.FEED_UNAVAILABLE)

        card = render_transit_card(report, MOMENT, is_live=True)

        self.assertEqual(
            card,
            "⚠️ трекінг транспорту зараз не працює\n\n<i>оновлюється · станом на 09:00</i>",
        )

    def test_render_transit_card_when_frozen_swaps_the_footer_for_a_manual_refresh_hint(self):
        card = render_transit_card(self.build_arrivals_report(), MOMENT, is_live=False)

        self.assertEqual(
            card,
            "найближчий: 🚎 3 за ~4 хв (~1.1 км) · 🚌 69 ~9 хв · 🚎 9К поки не видно\n\n"
            "<i>станом на 09:00 · 🔄 щоб оновити</i>",
        )


class ExceedsCaptionLimitTestCase(unittest.TestCase):
    def test_exceeds_caption_limit_at_the_limit_returns_false(self):
        text = "я" * 1024

        result = exceeds_caption_limit(text)

        self.assertFalse(result)

    def test_exceeds_caption_limit_one_character_over_the_limit_returns_true(self):
        text = "я" * 1025

        result = exceeds_caption_limit(text)

        self.assertTrue(result)

    def test_exceeds_caption_limit_counts_non_bmp_emoji_as_two_units(self):
        text = "🌿" * 513

        result = exceeds_caption_limit(text)

        self.assertTrue(result)

    def test_exceeds_caption_limit_for_empty_text_returns_false(self):
        result = exceeds_caption_limit("")

        self.assertFalse(result)
