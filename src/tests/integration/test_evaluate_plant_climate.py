from datetime import datetime, timedelta, timezone

from src.common.constants import ClimateComfortTransition, ClimateDimension, ClimateStatus
from src.modules.plant_care.domain import ClimateProblem
from src.modules.plant_care.use_cases.evaluate_plant_climate import EvaluatePlantClimateUseCase
from src.modules.room_climate.domain import RoomClimate
from src.tests.fakes import FixedRoomClimateSensor
from src.tests.integration.base import BaseIntegrationTestCase

ALERT_WINDOW_HOURS = 24
TEMPERATURE_HYSTERESIS_CELSIUS = 1.0
HUMIDITY_HYSTERESIS_PERCENT = 3.0


class EvaluatePlantClimateTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        # the use case stamps its own reading with the real clock, so windows are seeded against it
        self.now = datetime.now(timezone.utc)

    def build_use_case(self, temperature: float | None, humidity: float | None) -> EvaluatePlantClimateUseCase:
        climate = None
        if temperature is not None and humidity is not None:
            climate = RoomClimate(temperature_celsius=temperature, relative_humidity_percent=humidity)

        return EvaluatePlantClimateUseCase(
            uow=self.uow,
            sensor=FixedRoomClimateSensor(climate),
            household_calendar=self.household_calendar,
            alert_window_hours=ALERT_WINDOW_HOURS,
            temperature_hysteresis_celsius=TEMPERATURE_HYSTERESIS_CELSIUS,
            humidity_hysteresis_percent=HUMIDITY_HYSTERESIS_PERCENT,
        )

    async def seed_window(self, temperature: float, humidity: float, until: datetime | None = None) -> None:
        await self.seed_room_climate_readings(
            humidity_percent=humidity,
            temperature_celsius=temperature,
            since=self.now - timedelta(hours=ALERT_WINDOW_HOURS),
            until=until or self.now - timedelta(minutes=1),
        )

    async def seed_plant_wanting_humidity(self, low: float = 50.0, high: float = 70.0) -> int:
        return await self.seed_plant(name="Кактус", ideal_humidity_min_percent=low, ideal_humidity_max_percent=high)

    async def seed_plant_wanting_both(self) -> int:
        return await self.seed_plant(
            name="Кактус",
            ideal_temperature_min_celsius=18.0,
            ideal_temperature_max_celsius=27.0,
            ideal_humidity_min_percent=50.0,
            ideal_humidity_max_percent=70.0,
        )

    async def test_evaluate_plant_climate_folds_the_day_into_a_summary_that_outlives_the_raw_readings(self):
        """The raw table keeps two days; a photo six weeks old is judged against this row, not against those."""
        await self.build_use_case(temperature=25.0, humidity=44.0)()

        async with self.uow as uow:
            days = await uow.room_climate_days.list_between(self.today, self.today)

        self.assertEqual([day.day for day in days], [self.today])
        self.assertEqual(days[0].average_temperature_celsius, 25.0)
        self.assertEqual(days[0].average_humidity_percent, 44.0)

    async def test_evaluate_plant_climate_rewrites_the_day_as_more_readings_arrive(self):
        await self.build_use_case(temperature=20.0, humidity=40.0)()

        await self.build_use_case(temperature=30.0, humidity=60.0)()

        async with self.uow as uow:
            days = await uow.room_climate_days.list_between(self.today, self.today)
        self.assertEqual(len(days), 1)
        self.assertEqual(days[0].minimum_temperature_celsius, 20.0)
        self.assertEqual(days[0].maximum_temperature_celsius, 30.0)
        self.assertEqual(days[0].average_temperature_celsius, 25.0)

    async def test_evaluate_plant_climate_without_a_sensor_reports_nothing(self):
        await self.seed_plant_wanting_humidity()

        changes = await self.build_use_case(temperature=None, humidity=None)()

        self.assertEqual(changes, [])
        self.assertEqual(await self.retrieve_plant_climate_alerts(), [])

    async def test_evaluate_plant_climate_before_the_window_is_full_reports_nothing(self):
        await self.seed_plant_wanting_humidity()

        changes = await self.build_use_case(temperature=22.0, humidity=20.0)()

        self.assertEqual(changes, [])
        self.assertEqual(await self.retrieve_plant_climate_alerts(), [])

    async def test_evaluate_plant_climate_dry_for_a_whole_day_reports_the_plant_uncomfortable_once(self):
        await self.seed_plant_wanting_humidity()
        await self.seed_window(temperature=22.0, humidity=32.0)

        changes = await self.build_use_case(temperature=22.0, humidity=32.0)()

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].plant_name, "Кактус")
        self.assertEqual(changes[0].transition, ClimateComfortTransition.BECAME_UNCOMFORTABLE)
        self.assertEqual(
            changes[0].problems,
            [
                ClimateProblem(
                    dimension=ClimateDimension.HUMIDITY,
                    status=ClimateStatus.TOO_LOW,
                    value=32.0,
                    ideal_min=50.0,
                    ideal_max=70.0,
                )
            ],
        )
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 1)

    async def test_evaluate_plant_climate_dry_for_a_second_day_stays_silent(self):
        await self.seed_plant_wanting_humidity()
        await self.seed_window(temperature=22.0, humidity=32.0)
        await self.build_use_case(temperature=22.0, humidity=32.0)()

        changes = await self.build_use_case(temperature=22.0, humidity=31.0)()

        self.assertEqual(changes, [])
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 1)

    async def test_evaluate_plant_climate_still_dry_after_a_week_stays_silent(self):
        plant_id = await self.seed_plant_wanting_humidity()
        await self.seed_plant_climate_alert(
            plant_id, ClimateDimension.HUMIDITY, ClimateStatus.TOO_LOW, 32.0, self.now - timedelta(days=8)
        )
        await self.seed_window(temperature=22.0, humidity=32.0)

        changes = await self.build_use_case(temperature=22.0, humidity=32.0)()

        self.assertEqual(changes, [])
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 1)

    async def test_evaluate_plant_climate_recovering_for_a_whole_day_reports_the_plant_comfortable(self):
        await self.seed_plant_wanting_humidity()
        await self.seed_window(temperature=22.0, humidity=32.0)
        await self.build_use_case(temperature=22.0, humidity=32.0)()
        await self.seed_window(temperature=22.0, humidity=60.0, until=self.now)

        changes = await self.build_use_case(temperature=22.0, humidity=60.0)()

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].transition, ClimateComfortTransition.BECAME_COMFORTABLE)
        self.assertEqual(changes[0].problems, [])
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 2)

    async def test_evaluate_plant_climate_recovering_just_inside_the_floor_holds_the_alert(self):
        await self.seed_plant_wanting_humidity()
        await self.seed_window(temperature=22.0, humidity=32.0)
        await self.build_use_case(temperature=22.0, humidity=32.0)()
        await self.seed_window(temperature=22.0, humidity=51.0, until=self.now)

        changes = await self.build_use_case(temperature=22.0, humidity=51.0)()

        self.assertEqual(changes, [])
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 1)

    async def test_evaluate_plant_climate_ignores_a_single_shower_spike(self):
        await self.seed_plant_wanting_humidity()
        await self.seed_window(temperature=22.0, humidity=32.0)
        await self.build_use_case(temperature=22.0, humidity=32.0)()

        changes = await self.build_use_case(temperature=22.0, humidity=90.0)()

        self.assertEqual(changes, [])
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 1)

    async def test_evaluate_plant_climate_too_hot_reports_the_temperature_problem(self):
        await self.seed_plant(name="Плющ", ideal_temperature_min_celsius=18.0, ideal_temperature_max_celsius=27.0)
        await self.seed_window(temperature=30.0, humidity=50.0)

        changes = await self.build_use_case(temperature=30.0, humidity=50.0)()

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].plant_name, "Плющ")
        self.assertEqual(changes[0].transition, ClimateComfortTransition.BECAME_UNCOMFORTABLE)
        self.assertEqual(
            changes[0].problems,
            [
                ClimateProblem(
                    dimension=ClimateDimension.TEMPERATURE,
                    status=ClimateStatus.TOO_HIGH,
                    value=30.0,
                    ideal_min=18.0,
                    ideal_max=27.0,
                )
            ],
        )

    async def test_evaluate_plant_climate_without_a_range_never_evaluates_the_plant(self):
        await self.seed_plant(name="Байдужа")
        await self.seed_window(temperature=22.0, humidity=20.0)

        changes = await self.build_use_case(temperature=22.0, humidity=20.0)()

        self.assertEqual(changes, [])
        self.assertEqual(await self.retrieve_plant_climate_alerts(), [])

    async def test_evaluate_plant_climate_out_on_both_dimensions_reports_one_change_with_both_problems(self):
        await self.seed_plant_wanting_both()
        await self.seed_window(temperature=30.0, humidity=30.0)

        changes = await self.build_use_case(temperature=30.0, humidity=30.0)()

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].transition, ClimateComfortTransition.BECAME_UNCOMFORTABLE)
        self.assertEqual(
            {(problem.dimension, problem.status) for problem in changes[0].problems},
            {
                (ClimateDimension.TEMPERATURE, ClimateStatus.TOO_HIGH),
                (ClimateDimension.HUMIDITY, ClimateStatus.TOO_LOW),
            },
        )
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 2)

    async def test_evaluate_plant_climate_gaining_a_second_problem_reports_still_uncomfortable_with_both(self):
        plant_id = await self.seed_plant_wanting_both()
        await self.seed_plant_climate_alert(
            plant_id, ClimateDimension.TEMPERATURE, ClimateStatus.TOO_HIGH, 30.0, self.now - timedelta(hours=1)
        )
        await self.seed_window(temperature=30.0, humidity=30.0)

        changes = await self.build_use_case(temperature=30.0, humidity=30.0)()

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].transition, ClimateComfortTransition.STILL_UNCOMFORTABLE)
        self.assertEqual(
            {(problem.dimension, problem.status) for problem in changes[0].problems},
            {
                (ClimateDimension.TEMPERATURE, ClimateStatus.TOO_HIGH),
                (ClimateDimension.HUMIDITY, ClimateStatus.TOO_LOW),
            },
        )
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 2)

    async def test_evaluate_plant_climate_one_problem_clearing_while_another_stays_reports_still_uncomfortable(self):
        plant_id = await self.seed_plant_wanting_both()
        await self.seed_plant_climate_alert(
            plant_id, ClimateDimension.TEMPERATURE, ClimateStatus.TOO_HIGH, 30.0, self.now - timedelta(hours=1)
        )
        await self.seed_plant_climate_alert(
            plant_id, ClimateDimension.HUMIDITY, ClimateStatus.TOO_LOW, 30.0, self.now - timedelta(hours=1)
        )
        await self.seed_window(temperature=22.0, humidity=30.0)

        changes = await self.build_use_case(temperature=22.0, humidity=30.0)()

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].transition, ClimateComfortTransition.STILL_UNCOMFORTABLE)
        self.assertEqual(
            changes[0].problems,
            [
                ClimateProblem(
                    dimension=ClimateDimension.HUMIDITY,
                    status=ClimateStatus.TOO_LOW,
                    value=30.0,
                    ideal_min=50.0,
                    ideal_max=70.0,
                )
            ],
        )
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 3)
