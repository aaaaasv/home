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
        return RetrievePlantSheetUseCase(uow=self.uow, household_calendar=self.household_calendar)(self.plant_id)

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

        page = render_plant_sheet(await self.sheet(), lambda photo_id: f"/photo/{photo_id}", "Домовик", can_act=False)

        self.assertIn("Кактус", page)
        self.assertIn("Nepenthes", page)
        self.assertIn("Домовик", page)
        self.assertIn(roman_date(FROZEN_NOW - timedelta(days=30)), page)

    async def test_render_without_the_key_offers_no_watering_button(self):
        page = render_plant_sheet(await self.sheet(), lambda photo_id: "", "Домовик", can_act=False)

        self.assertNotIn("Записати полив", page)

    async def test_render_with_the_key_offers_the_watering_button(self):
        page = render_plant_sheet(await self.sheet(), lambda photo_id: "", "Домовик", can_act=True)

        self.assertIn("Записати полив", page)

    async def test_render_a_plant_that_has_photos_shows_the_specimen_and_the_strip(self):
        photo_id = await self.seed_plant_photo(self.plant_id, telegram_file_id="file-1")

        page = render_plant_sheet(await self.sheet(), lambda pid: f"/photo/{pid}", "Домовик", can_act=False)

        self.assertIn(f'src="/photo/{photo_id}"', page)
        self.assertIn('class="mount"', page)
