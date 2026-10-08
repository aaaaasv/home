from datetime import datetime, timedelta, timezone

from src.bot.handlers.plants.review_tools import PlantReviewTools
from src.common.constants import CareTaskType
from src.infrastructure.db.uow import UnitOfWork
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase


class PlantReviewToolsTestCase(BaseIntegrationTestCase):
    """
    What the review may look up for itself, and what it may not.

    everything here is about one plant. a reviewer that could wander the whole collection would be handed
    other plants' records to explain this one's leaf, which is how a confident wrong answer gets written.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Марті", room="кухня-вітальня")
        self.tools = PlantReviewTools(
            plant_id=self.plant_id, uow_factory=self.uow_factory, household_calendar=self.household_calendar
        )

    async def test_list_photos_names_every_frame_with_its_date_and_kind(self):
        await self.seed_plant_photo(
            plant_id=self.plant_id,
            local_path="/photos/one.jpg",
            frame="overview",
            taken_at=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        )
        await self.seed_plant_photo(
            plant_id=self.plant_id,
            local_path="/photos/two.jpg",
            frame="detail",
            telegram_file_unique_id="unique-b",
            taken_at=datetime(2026, 7, 1, 10, 5, tzinfo=timezone.utc),
        )

        listed = await self.tools.run("list_photos", {})

        self.assertEqual(
            listed,
            "id=1 · 1 липня 2026 · overview\nid=2 · 1 липня 2026 · detail",
        )

    async def test_list_photos_for_a_plant_with_none_says_so(self):
        self.assertEqual(await self.tools.run("list_photos", {}), "Збережених знімків немає.")

    async def test_view_photo_of_another_plant_is_refused(self):
        """One review, one plant: another plant's leaf must not be used to explain this one's."""
        other_plant_id = await self.seed_plant(name="Кроко")
        await self.seed_plant_photo(plant_id=other_plant_id, local_path="/photos/other.jpg")

        answer = await self.tools.run("view_photo", {"photo_id": 1})

        self.assertEqual(answer, "Такого знімка в цієї рослини немає.")

    async def test_view_photo_whose_file_is_gone_says_so_rather_than_failing(self):
        await self.seed_plant_photo(plant_id=self.plant_id, local_path="/photos/gone.jpg")

        answer = await self.tools.run("view_photo", {"photo_id": 1})

        self.assertEqual(answer, "Файл цього знімка не читається.")

    async def test_care_log_lists_what_was_really_done_and_by_whom(self):
        await self.seed_care_event(
            plant_id=self.plant_id,
            task_type=CareTaskType.WATERING,
            performed_at=FROZEN_NOW - timedelta(days=2),
            performed_by_display_name="Тест",
        )

        logged = await self.tools.run("care_log", {})

        self.assertEqual(logged, "10 липня 2026 · полив · Тест")

    async def test_care_log_for_a_plant_nobody_has_touched_says_so(self):
        self.assertEqual(await self.tools.run("care_log", {}), "Доглядових записів немає.")

    async def test_room_climate_reports_the_days_the_sensor_recorded(self):
        await self.seed_climate_day(day=FROZEN_NOW.date(), temperature=24.0, humidity=41.0)

        reported = await self.tools.run("room_climate", {"days": 7})

        self.assertEqual(reported, "12 липня 2026 · 24–24°C · 41–41%")

    async def test_room_climate_for_a_plant_with_no_room_says_why_it_cannot(self):
        roomless_id = await self.seed_plant(name="Бубик", room=None)
        tools = PlantReviewTools(
            plant_id=roomless_id, uow_factory=self.uow_factory, household_calendar=self.household_calendar
        )

        self.assertEqual(
            await tools.run("room_climate", {"days": 7}),
            "У цієї рослини не вказана кімната, тож погоди по ній немає.",
        )

    async def test_a_tool_nobody_defined_is_refused_rather_than_crashing(self):
        self.assertEqual(await self.tools.run("delete_everything", {}), "Такого інструмента немає.")
