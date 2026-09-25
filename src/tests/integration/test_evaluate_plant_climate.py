from datetime import datetime, timedelta

from src.common.constants import ClimateComfortTransition, ClimateDimension, ClimateStatus
from src.modules.plant_care.domain import ClimateProblem
from src.modules.plant_care.use_cases.evaluate_plant_climate import EvaluatePlantClimateUseCase
from src.tests.integration.base import BaseIntegrationTestCase

ALERT_WINDOW_HOURS = 24
TEMPERATURE_HYSTERESIS_CELSIUS = 1.0
HUMIDITY_HYSTERESIS_PERCENT = 3.0

BEDROOM = "спальня"
LIVING_ROOM = "кухня-вітальня"


class EvaluatePlantClimateTestCase(BaseIntegrationTestCase):
    """
    Comfort is decided per room, so the room a plant is in is now part of every answer here.

    the rule that matters most is the silent one: a plant whose room the bot cannot hear gets no verdict at
    all. for a month every plant was judged by the air of the server shelf, and it never looked wrong because
    the number was plausible.
    """

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.now = self.household_calendar.now()

    def build_use_case(self) -> EvaluatePlantClimateUseCase:
        return EvaluatePlantClimateUseCase(
            uow=self.uow,
            household_calendar=self.household_calendar,
            alert_window_hours=ALERT_WINDOW_HOURS,
            temperature_hysteresis_celsius=TEMPERATURE_HYSTERESIS_CELSIUS,
            humidity_hysteresis_percent=HUMIDITY_HYSTERESIS_PERCENT,
        )

    async def seed_window(
        self, temperature: float, humidity: float, room: str = BEDROOM, until: datetime | None = None
    ) -> None:
        await self.seed_sensor_readings(
            room=room,
            temperature_celsius=temperature,
            humidity_percent=humidity,
            since=self.now - timedelta(hours=ALERT_WINDOW_HOURS),
            until=until or self.now,
        )

    async def seed_plant_wanting_humidity(self, room: str | None = BEDROOM) -> int:
        return await self.seed_plant(
            name="Кактус", room=room, ideal_humidity_min_percent=50.0, ideal_humidity_max_percent=70.0
        )

    async def seed_plant_wanting_both(self, room: str | None = BEDROOM) -> int:
        return await self.seed_plant(
            name="Кактус",
            room=room,
            ideal_temperature_min_celsius=18.0,
            ideal_temperature_max_celsius=27.0,
            ideal_humidity_min_percent=50.0,
            ideal_humidity_max_percent=70.0,
        )

    async def test_evaluate_plant_climate_for_a_plant_with_no_room_reports_nothing(self):
        await self.seed_plant_wanting_humidity(room=None)
        await self.seed_window(temperature=22.0, humidity=32.0)

        changes = await self.build_use_case()()

        self.assertEqual(changes, [])
        self.assertEqual(await self.retrieve_plant_climate_alerts(), [])

    async def test_evaluate_plant_climate_whose_room_has_no_sensor_reports_nothing(self):
        await self.seed_plant_wanting_humidity(room=LIVING_ROOM)
        await self.seed_window(temperature=22.0, humidity=32.0, room=BEDROOM)

        changes = await self.build_use_case()()

        self.assertEqual(changes, [])
        self.assertEqual(await self.retrieve_plant_climate_alerts(), [])

    async def test_evaluate_plant_climate_judges_each_plant_by_the_air_of_its_own_room(self):
        await self.seed_plant(
            name="Кактус", room=BEDROOM, ideal_humidity_min_percent=50.0, ideal_humidity_max_percent=70.0
        )
        await self.seed_plant(
            name="Плющ", room=LIVING_ROOM, ideal_humidity_min_percent=50.0, ideal_humidity_max_percent=70.0
        )
        await self.seed_window(temperature=22.0, humidity=32.0, room=BEDROOM)
        await self.seed_window(temperature=22.0, humidity=60.0, room=LIVING_ROOM)

        changes = await self.build_use_case()()

        self.assertEqual([change.plant_name for change in changes], ["Кактус"])
        self.assertEqual(changes[0].problems[0].value, 32.0)

    async def test_evaluate_plant_climate_before_the_window_is_full_reports_nothing(self):
        await self.seed_plant_wanting_humidity()
        await self.seed_sensor_readings(
            room=BEDROOM,
            temperature_celsius=22.0,
            humidity_percent=20.0,
            since=self.now - timedelta(hours=2),
            until=self.now,
        )

        changes = await self.build_use_case()()

        self.assertEqual(changes, [])
        self.assertEqual(await self.retrieve_plant_climate_alerts(), [])

    async def test_evaluate_plant_climate_with_one_lone_reading_reports_nothing(self):
        await self.seed_plant_wanting_humidity()
        await self.seed_sensor_readings(
            room=BEDROOM, temperature_celsius=22.0, humidity_percent=20.0, since=self.now, until=self.now
        )

        changes = await self.build_use_case()()

        self.assertEqual(changes, [])

    async def test_evaluate_plant_climate_dry_for_a_whole_day_reports_the_plant_uncomfortable_once(self):
        await self.seed_plant_wanting_humidity()
        await self.seed_window(temperature=22.0, humidity=32.0)

        changes = await self.build_use_case()()

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
        await self.build_use_case()()

        changes = await self.build_use_case()()

        self.assertEqual(changes, [])
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 1)

    async def test_evaluate_plant_climate_still_dry_after_a_week_stays_silent(self):
        plant_id = await self.seed_plant_wanting_humidity()
        await self.seed_plant_climate_alert(
            plant_id, ClimateDimension.HUMIDITY, ClimateStatus.TOO_LOW, 32.0, self.now - timedelta(days=8)
        )
        await self.seed_window(temperature=22.0, humidity=32.0)

        changes = await self.build_use_case()()

        self.assertEqual(changes, [])
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 1)

    async def test_evaluate_plant_climate_recovering_for_a_whole_day_reports_the_plant_comfortable(self):
        await self.seed_plant_wanting_humidity()
        await self.seed_window(temperature=22.0, humidity=32.0)
        await self.build_use_case()()
        await self.clear_sensor_readings()
        await self.seed_window(temperature=22.0, humidity=60.0)

        changes = await self.build_use_case()()

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].transition, ClimateComfortTransition.BECAME_COMFORTABLE)
        self.assertEqual(changes[0].problems, [])
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 2)

    async def test_evaluate_plant_climate_recovering_just_inside_the_floor_holds_the_alert(self):
        await self.seed_plant_wanting_humidity()
        await self.seed_window(temperature=22.0, humidity=32.0)
        await self.build_use_case()()
        await self.clear_sensor_readings()
        await self.seed_window(temperature=22.0, humidity=51.0)

        changes = await self.build_use_case()()

        self.assertEqual(changes, [])
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 1)

    async def test_evaluate_plant_climate_ignores_a_single_shower_spike(self):
        await self.seed_plant_wanting_humidity()
        await self.seed_window(temperature=22.0, humidity=32.0)
        await self.build_use_case()()
        await self.seed_sensor_readings(
            room=BEDROOM, temperature_celsius=22.0, humidity_percent=90.0, since=self.now, until=self.now
        )

        changes = await self.build_use_case()()

        self.assertEqual(changes, [])
        self.assertEqual(len(await self.retrieve_plant_climate_alerts()), 1)

    async def test_evaluate_plant_climate_too_hot_reports_the_temperature_problem(self):
        await self.seed_plant(
            name="Плющ", room=BEDROOM, ideal_temperature_min_celsius=18.0, ideal_temperature_max_celsius=27.0
        )
        await self.seed_window(temperature=30.0, humidity=50.0)

        changes = await self.build_use_case()()

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
        await self.seed_plant(name="Байдужа", room=BEDROOM)
        await self.seed_window(temperature=22.0, humidity=20.0)

        changes = await self.build_use_case()()

        self.assertEqual(changes, [])
        self.assertEqual(await self.retrieve_plant_climate_alerts(), [])

    async def test_evaluate_plant_climate_out_on_both_dimensions_reports_one_change_with_both_problems(self):
        await self.seed_plant_wanting_both()
        await self.seed_window(temperature=30.0, humidity=30.0)

        changes = await self.build_use_case()()

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

        changes = await self.build_use_case()()

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

        changes = await self.build_use_case()()

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
