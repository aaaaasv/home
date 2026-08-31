from datetime import timedelta

from src.common.constants import CareTaskType
from src.modules.plant_care.use_cases.retrieve_drawer import RetrieveDrawerUseCase
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase
from src.web.rendering import find_neighbours, render_drawer


class DrawerTestCase(BaseIntegrationTestCase):
    def drawer(self):
        return RetrieveDrawerUseCase(uow=self.uow, household_calendar=self.household_calendar)()

    async def seed_plant_due_in(self, name: str, days: int, **overrides) -> int:
        plant_id = await self.seed_plant(name=name, created_at=FROZEN_NOW - timedelta(days=20), **overrides)
        await self.seed_care_schedule(
            plant_id=plant_id,
            task_type=CareTaskType.WATERING,
            interval_days=6,
            next_due_on=self.today + timedelta(days=days),
        )
        return plant_id

    async def test_drawer_lists_every_living_plant_alphabetically_with_the_days_until_its_watering(self):
        await self.seed_plant_due_in("Тігл", 3, slug="tihl")
        await self.seed_plant_due_in("Амазонка", -2, slug="amazonka")

        entries = await self.drawer()

        # a card catalogue is filed by name, and list_active already orders that way
        self.assertEqual(
            [(entry.name, entry.slug, entry.days_until_watering, entry.age_days) for entry in entries],
            [("Амазонка", "amazonka", -2, 20), ("Тігл", "tihl", 3, 20)],
        )

    async def test_drawer_entry_without_a_watering_schedule_reports_no_due_day(self):
        await self.seed_plant(name="Пепероні", slug="peperoni", created_at=FROZEN_NOW)

        entries = await self.drawer()

        self.assertEqual([(entry.name, entry.days_until_watering) for entry in entries], [("Пепероні", None)])

    async def test_drawer_entry_carries_the_newest_photo_as_its_cover(self):
        plant_id = await self.seed_plant_due_in("Тігл", 1, slug="tihl")
        await self.seed_plant_photo(plant_id, taken_at=FROZEN_NOW - timedelta(days=5))
        newest_photo_id = await self.seed_plant_photo(plant_id, taken_at=FROZEN_NOW - timedelta(hours=1))

        entries = await self.drawer()

        self.assertEqual([entry.cover_photo_id for entry in entries], [newest_photo_id])

    async def test_render_drawer_gives_every_plant_a_folder_that_links_to_its_sheet(self):
        await self.seed_plant_due_in("Тігл", 3, slug="tihl")
        await self.seed_plant_due_in("Амазонка", 0, slug="amazonka")

        page = render_drawer(await self.drawer(), lambda photo_id: f"/photo/{photo_id}", "Домовик")

        self.assertIn('href="/p/tihl" data-tab="Тігл"', page)
        self.assertIn('href="/p/amazonka" data-tab="Амазонка"', page)
        self.assertIn("полив за 3 дн.", page)
        self.assertIn('<span class="due now">полив сьогодні</span>', page)

    async def test_render_drawer_says_how_overdue_a_watering_is(self):
        await self.seed_plant_due_in("Тігл", -4, slug="tihl")

        page = render_drawer(await self.drawer(), lambda photo_id: "", "Домовик")

        self.assertIn('<span class="due now">полив прострочено на 4 дн.</span>', page)

    async def test_find_neighbours_gives_a_middle_sheet_a_folder_on_either_side(self):
        await self.seed_plant_due_in("Тігл", 1, slug="tihl")
        await self.seed_plant_due_in("Амазонка", 1, slug="amazonka")
        middle_id = await self.seed_plant_due_in("Пепероні", 1, slug="peperoni")
        entries = await self.drawer()

        previous, following = find_neighbours(entries, middle_id)

        self.assertEqual((previous.name, following.name), ("Амазонка", "Тігл"))

    async def test_find_neighbours_leaves_the_last_sheet_without_one_ahead_of_it(self):
        await self.seed_plant_due_in("Амазонка", 1, slug="amazonka")
        last_id = await self.seed_plant_due_in("Тігл", 1, slug="tihl")
        entries = await self.drawer()

        previous, following = find_neighbours(entries, last_id)

        self.assertEqual((previous.name, following), ("Амазонка", None))

    async def test_drawer_files_a_name_starting_with_i_after_one_starting_with_a(self):
        await self.seed_plant_due_in("Ізабелла", 1, slug="izabella")
        await self.seed_plant_due_in("Амазонка", 1, slug="amazonka")
        await self.seed_plant_due_in("Ялинка", 1, slug="yalynka")

        entries = await self.drawer()

        # codepoint order would put Ізабелла first, because і (U+0406) sits below а (U+0410)
        self.assertEqual([entry.name for entry in entries], ["Амазонка", "Ізабелла", "Ялинка"])


class DrawerArchivedPlantTestCase(BaseIntegrationTestCase):
    """
    A plant that died stays in the drawer.

    the herbarium is a record, not an inventory: removing the sheet would erase the care history that is the
    whole reason it exists, and the tag on the pot would start answering 404.
    """

    def drawer(self):
        return RetrieveDrawerUseCase(uow=self.uow, household_calendar=self.household_calendar)()

    async def seed_archived(self, name: str, slug: str) -> int:
        plant_id = await self.seed_plant(
            name=name, slug=slug, is_archived=True, created_at=FROZEN_NOW - timedelta(days=30)
        )
        await self.seed_care_schedule(
            plant_id=plant_id,
            task_type=CareTaskType.WATERING,
            interval_days=8,
            next_due_on=self.today + timedelta(days=2),
        )
        return plant_id

    async def test_drawer_files_an_archived_plant_among_the_living_ones_alphabetically(self):
        await self.seed_plant(name="Тігл", slug="tihl", created_at=FROZEN_NOW - timedelta(days=30))
        await self.seed_archived("Ізабелла", "izabella")

        entries = await self.drawer()

        self.assertEqual(
            [(entry.name, entry.is_archived) for entry in entries],
            [("Ізабелла", True), ("Тігл", False)],
        )

    async def test_drawer_entry_for_an_archived_plant_reports_no_watering_although_its_schedule_remains(self):
        await self.seed_archived("Ізабелла", "izabella")

        entries = await self.drawer()

        self.assertEqual([(entry.name, entry.days_until_watering) for entry in entries], [("Ізабелла", None)])

    async def test_render_drawer_greys_an_archived_folder_and_marks_it_instead_of_a_due_day(self):
        await self.seed_archived("Ізабелла", "izabella")

        page = render_drawer(await self.drawer(), lambda photo_id: f"/photo/{photo_id}", "Домовик")

        self.assertIn('<a class="file gone" href="/p/izabella"', page)
        self.assertIn('<span class="gone">більше не з нами</span>', page)
        self.assertNotIn("полив за", page)

    async def test_render_drawer_leaves_a_living_folder_unmarked(self):
        await self.seed_plant(name="Тігл", slug="tihl", created_at=FROZEN_NOW)

        page = render_drawer(await self.drawer(), lambda photo_id: f"/photo/{photo_id}", "Домовик")

        self.assertIn('<a class="file" href="/p/tihl"', page)
        self.assertNotIn("більше не з нами", page)
