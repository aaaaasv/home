from datetime import timedelta

from src.common.constants import CareTaskType
from src.modules.plant_care.commands import RecordCareEventCommand
from src.modules.plant_care.use_cases.record_care_event import RecordCareEventUseCase
from src.modules.plant_care.use_cases.retrieve_plant_sheet import RetrievePlantSheetUseCase
from src.tests.factories import OWNER, PARTNER
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase
from src.web.rendering import render_plant_sheet, roman_date


class PlantSheetTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(
            name="Кактус",
            species="Nepenthes",
            created_at=FROZEN_NOW - timedelta(days=30),
            ideal_humidity_min_percent=42.0,
            ideal_humidity_max_percent=90.0,
        )
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=3, next_due_on=self.today
        )

    def sheet(self):
        return RetrievePlantSheetUseCase(uow=self.uow, household_calendar=self.household_calendar)(str(self.plant_id))

    async def water(self, actor, performed_at):
        await RecordCareEventUseCase(
            uow=self.uow, actor=actor, household_calendar=self.household_calendar, recent_care_guard_hours=12
        )(
            RecordCareEventCommand(
                plant_id=self.plant_id, task_type=CareTaskType.WATERING, performed_at=performed_at, force=True
            )
        )

    async def test_sheet_counts_the_days_the_plant_has_been_in_the_house(self):
        sheet = await self.sheet()

        self.assertEqual(sheet.age_days, 30)

    async def test_sheet_tallies_each_person_who_watered_it(self):
        await self.water(OWNER, FROZEN_NOW - timedelta(days=9))
        await self.water(PARTNER, FROZEN_NOW - timedelta(days=6))
        await self.water(PARTNER, FROZEN_NOW - timedelta(days=3))

        sheet = await self.sheet()

        self.assertEqual([(c.name, c.count) for c in sheet.carers], [("Марта", 2), ("Богдан", 1)])

    async def test_sheet_measures_the_gaps_between_waterings(self):
        await self.water(OWNER, FROZEN_NOW - timedelta(days=9))
        await self.water(OWNER, FROZEN_NOW - timedelta(days=6))
        await self.water(OWNER, FROZEN_NOW - timedelta(days=2))

        sheet = await self.sheet()

        self.assertEqual(sheet.watering_gaps_days, [3.0, 4.0])

    async def test_sheet_reports_humidity_below_the_ideal_minimum(self):
        await self.seed_room_climate_readings(
            humidity_percent=41.0, since=FROZEN_NOW - timedelta(hours=2), until=FROZEN_NOW, temperature_celsius=25.0
        )

        sheet = await self.sheet()

        self.assertTrue(sheet.humidity_is_low)

    async def test_render_puts_the_plant_and_its_binomial_on_the_page(self):
        await self.water(OWNER, FROZEN_NOW - timedelta(days=2))

        page = render_plant_sheet(await self.sheet(), lambda photo_id: f"/photo/{photo_id}", "Домовик")

        self.assertIn("Кактус", page)
        self.assertIn("Nepenthes", page)
        self.assertIn("Домовик", page)
        self.assertIn(roman_date(FROZEN_NOW - timedelta(days=30)), page)

    async def test_render_gives_every_actionable_care_type_its_own_confirming_button(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.FERTILIZING, interval_days=14, next_due_on=self.today
        )

        page = render_plant_sheet(await self.sheet(), lambda photo_id: "", "Система")

        self.assertIn('<form method="post" action="care/watering"><button type="submit">Так, записати</button>', page)
        self.assertIn('<form method="post" action="care/fertilizing">', page)
        self.assertIn("<summary>Полито</summary>", page)
        self.assertIn("<summary>Підживлено</summary>", page)

    async def test_render_offers_no_button_for_a_photo_because_a_page_cannot_take_one(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.PHOTO, interval_days=30, next_due_on=self.today
        )

        page = render_plant_sheet(await self.sheet(), lambda photo_id: "", "Система")

        self.assertIn("Знімок", page)
        self.assertNotIn('action="care/photo"', page)

    async def test_render_tells_the_watering_story_only_inside_the_regimen(self):
        page = render_plant_sheet(await self.sheet(), lambda photo_id: "", "Система")

        # the label used to repeat the schedule the regimen already owns
        self.assertNotIn("<dt>Полив</dt>", page)
        self.assertNotIn("<dt>Пересадка</dt>", page)
        self.assertEqual(page.count('action="care/watering"'), 1)

    async def test_render_asks_for_no_password_at_all(self):
        page = render_plant_sheet(await self.sheet(), lambda photo_id: "", "Домовик")

        self.assertNotIn('type="password"', page)
        self.assertNotIn('name="password"', page)
        self.assertNotIn("Пароль", page)

    async def test_sheet_can_be_fetched_by_its_slug(self):
        async with self.uow as uow:
            plant = await uow.plants.retrieve(self.plant_id)
            plant.slug = "kaktus"

        sheet = await RetrievePlantSheetUseCase(uow=self.uow, household_calendar=self.household_calendar)("kaktus")

        self.assertEqual(sheet.id, self.plant_id)
        self.assertEqual(sheet.slug, "kaktus")

    async def test_render_a_plant_that_has_photos_shows_the_specimen_and_the_strip(self):
        photo_id = await self.seed_plant_photo(self.plant_id, telegram_file_id="file-1")

        page = render_plant_sheet(await self.sheet(), lambda pid: f"/photo/{pid}", "Домовик")

        self.assertIn(f'src="/photo/{photo_id}"', page)
        self.assertIn('class="mount"', page)

    async def test_render_declares_a_mobile_viewport_because_every_visit_arrives_from_a_phone(self):
        page = render_plant_sheet(await self.sheet(), lambda photo_id: "", "Домовик")

        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', page)
        self.assertTrue(page.startswith('<!doctype html>\n<html lang="uk">'))
        self.assertIn('<meta charset="utf-8">', page)
        self.assertTrue(page.rstrip().endswith("</html>"))

    async def test_sheet_credits_a_carer_by_the_name_they_chose_not_the_one_on_the_old_event(self):
        await self.water(OWNER, FROZEN_NOW - timedelta(days=3))
        async with self.uow as uow:
            await uow.family_members.upsert(OWNER.telegram_user_id, OWNER.display_name)
            (await uow.family_members.list_all())[0].preferred_name = "Богданчик"
            await uow.commit()

        sheet = await self.sheet()

        self.assertEqual([(carer.name, carer.count) for carer in sheet.carers], [("Богданчик", 1)])
        self.assertEqual([event.performed_by_display_name for event in sheet.recent_events], ["Богданчик"])

    async def test_render_puts_the_plants_own_name_on_the_folder_tab_not_a_fixed_family(self):
        page = render_plant_sheet(await self.sheet(), lambda photo_id: "", "Домовик")

        self.assertIn('<span class="tab here">Кактус</span>', page)
        self.assertNotIn("NEPENTHACEAE", page)

    async def test_render_marks_the_newest_plate_as_the_one_on_the_mount(self):
        await self.seed_plant_photo(self.plant_id, taken_at=FROZEN_NOW - timedelta(days=9))
        await self.seed_plant_photo(self.plant_id, taken_at=FROZEN_NOW - timedelta(days=1))

        page = render_plant_sheet(await self.sheet(), lambda photo_id: f"/photo/{photo_id}", "Домовик")

        self.assertEqual(page.count('data-caption="'), 2)
        self.assertIn('знімок 2 із 2" class="is-mounted"', page)
        self.assertIn('id="mounted"', page)

    async def test_render_compares_first_and_latest_plate_once_there_are_two(self):
        await self.seed_plant_photo(self.plant_id, taken_at=FROZEN_NOW - timedelta(days=9))
        await self.seed_plant_photo(self.plant_id, taken_at=FROZEN_NOW - timedelta(days=1))

        page = render_plant_sheet(await self.sheet(), lambda photo_id: f"/photo/{photo_id}", "Домовик")

        self.assertIn("Tabula IV · зріст", page)
        self.assertIn("за 8 діб", page)
        self.assertIn('id="wipe"', page)

    async def test_render_a_single_plate_offers_no_comparison_to_make(self):
        await self.seed_plant_photo(self.plant_id, taken_at=FROZEN_NOW - timedelta(days=1))

        page = render_plant_sheet(await self.sheet(), lambda photo_id: f"/photo/{photo_id}", "Домовик")

        self.assertNotIn("Tabula IV", page)
        self.assertNotIn('id="wipe"', page)

    async def test_render_hands_the_climate_readings_to_the_page_for_scrubbing(self):
        await self.seed_room_climate_readings(44.0, FROZEN_NOW - timedelta(hours=6), FROZEN_NOW)

        page = render_plant_sheet(await self.sheet(), lambda photo_id: "", "Домовик")

        self.assertIn('id="climate" data-points=', page)
        self.assertIn('id="climate-readout"', page)

    async def test_render_a_lone_plate_is_captioned_by_date_without_a_one_of_one_count(self):
        await self.seed_plant_photo(self.plant_id, taken_at=FROZEN_NOW - timedelta(days=1))

        page = render_plant_sheet(await self.sheet(), lambda photo_id: f"/photo/{photo_id}", "Домовик")

        self.assertIn('id="mount-caption">11.vii.2026</figcaption>', page)
        self.assertNotIn("знімок", page)

    async def test_render_names_fertilizing_the_way_a_gardener_would(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.FERTILIZING, interval_days=30, next_due_on=self.today
        )

        page = render_plant_sheet(await self.sheet(), lambda photo_id: "", "Система")

        self.assertIn("Підживлення", page)
        self.assertNotIn("Живлення<", page)

    async def test_render_puts_care_instructions_behind_a_details_button_on_their_own_row(self):
        async with self.uow as uow:
            schedule = await uow.care_schedules.retrieve_for_plant(self.plant_id, CareTaskType.WATERING)
            schedule.instructions = "Поливай, коли верхні 1–2 см ґрунту підсохли"
            await uow.commit()

        page = render_plant_sheet(await self.sheet(), lambda photo_id: "", "Система")

        self.assertIn('aria-controls="note-watering">Деталі</button>', page)
        self.assertIn('<div class="note" id="note-watering">Поливай, коли верхні 1–2 см ґрунту підсохли</div>', page)

    async def test_render_offers_no_details_button_for_care_with_no_instructions(self):
        page = render_plant_sheet(await self.sheet(), lambda photo_id: "", "Система")

        self.assertNotIn("Деталі", page)
        self.assertNotIn('class="note"', page)
