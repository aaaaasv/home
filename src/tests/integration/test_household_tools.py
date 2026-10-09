from datetime import timedelta

from src.bot.handlers.assistant.household_tools import HouseholdTools
from src.common.config import Settings
from src.infrastructure.db.uow import UnitOfWork
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase
from src.tests.telegram import ACTOR_ID


class HouseholdToolsTestCase(BaseIntegrationTestCase):
    """
    What the assistant can look up for itself.

    these answer the questions the facts dump could not: «коли ми востаннє були без світла», «в якій
    кімнаті найхолодніше», «скільки кондиціонер наробив», «куди ми ще не ходили». the data was in the
    database the whole time and nothing offered it.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.tools = HouseholdTools(
            uow_factory=self.uow_factory,
            household_calendar=self.household_calendar,
            settings=Settings(SENSOR_ROOMS='{"temp-room": "кухня-вітальня"}'),
        )

    async def test_grid_log_reads_back_when_the_light_went_and_came_back(self):
        async with self.uow as uow:
            await uow.grid_events.create({"state": "on_battery", "at": FROZEN_NOW - timedelta(hours=5)})
            await uow.grid_events.create({"state": "on_grid", "at": FROZEN_NOW - timedelta(hours=2)})

        logged = await self.tools.run("grid_log", {"days": 7})

        self.assertEqual(logged, "12 липня 2026 04:00 · світло зникло\n12 липня 2026 07:00 · світло є")

    async def test_grid_log_with_nothing_recorded_says_so_rather_than_claiming_calm(self):
        answer = await self.tools.run("grid_log", {"days": 7})

        self.assertEqual(answer, "За цей час світло не зникало й не з'являлось — або записів ще немає.")

    async def test_room_climate_reports_each_room_the_sensors_cover(self):
        await self.seed_climate_day(day=FROZEN_NOW.date(), temperature=21.0, humidity=44.0)

        reported = await self.tools.run("room_climate", {"days": 7})

        self.assertIn("— кухня-вітальня:", reported)
        self.assertIn("12 липня 2026 · 21–21°C · 44–44%", reported)

    async def test_room_climate_for_one_named_room_leaves_the_others_out(self):
        await self.seed_climate_day(day=FROZEN_NOW.date(), temperature=21.0, humidity=44.0)

        reported = await self.tools.run("room_climate", {"days": 7, "room": "спальня"})

        self.assertEqual(reported, "Датчики за цей період нічого не записали.")

    async def test_outdoor_weather_reads_back_the_day_rows(self):
        async with self.uow as uow:
            await uow.outdoor_weather_days.save_day(
                self.household_calendar.today(),
                {
                    "reading_count": 24,
                    "minimum_temperature_celsius": 8.0,
                    "maximum_temperature_celsius": 19.0,
                    "minimum_humidity_percent": 40.0,
                    "maximum_humidity_percent": 80.0,
                },
            )

        reported = await self.tools.run("outdoor_weather", {"days": 7})

        self.assertEqual(reported, "12 липня 2026 · 8–19°C · 40–80%")

    async def test_the_air_conditioner_log_gives_each_run_and_how_long_it_lasted(self):
        async with self.uow as uow:
            await uow.air_conditioner_runs.create(
                {"started_at": FROZEN_NOW - timedelta(hours=3), "ended_at": FROZEN_NOW - timedelta(hours=1)}
            )

        logged = await self.tools.run("air_conditioner_log", {"days": 30})

        self.assertEqual(logged, "12 липня 2026 06:00 · 120 хв")

    async def test_a_run_still_going_says_so_rather_than_guessing_a_length(self):
        async with self.uow as uow:
            await uow.air_conditioner_runs.create({"started_at": FROZEN_NOW - timedelta(hours=1), "ended_at": None})

        logged = await self.tools.run("air_conditioner_log", {"days": 30})

        self.assertEqual(logged, "12 липня 2026 08:00 · увімкнений досі")

    async def test_places_says_which_ones_are_still_ahead(self):
        async with self.uow as uow:
            await uow.places.create(
                {"name": "Музей води", "added_by_telegram_user_id": ACTOR_ID, "added_by_display_name": "Тест"}
            )
            await uow.places.create(
                {
                    "name": "Ботсад",
                    "added_by_telegram_user_id": ACTOR_ID,
                    "added_by_display_name": "Тест",
                    "visited_at": FROZEN_NOW,
                }
            )

        listed = await self.tools.run("places", {})

        self.assertEqual(listed, "— Музей води · ще не були\n— Ботсад · уже були")

    async def test_a_tool_nobody_defined_is_refused_rather_than_crashing(self):
        self.assertEqual(await self.tools.run("drop_everything", {}), "Такого інструмента немає.")

    async def test_a_window_longer_than_a_year_is_clamped_rather_than_trusted(self):
        """A model asking for ten thousand days must not turn into ten thousand days of rows."""
        answer = await self.tools.run("grid_log", {"days": 10_000})

        self.assertEqual(answer, "За цей час світло не зникало й не з'являлось — або записів ще немає.")
