from src.bot.handlers.plants.tools import PlantTools
from src.common.config import Settings
from src.common.constants import CareTaskType
from src.infrastructure.db.uow import UnitOfWork
from src.tests.integration.base import BaseIntegrationTestCase


class PlantToolsTestCase(BaseIntegrationTestCase):
    """
    Writing the plant card by talking about it: «сорт принцеси — lambada», «прибери місце з опису».

    the card was only editable by walking a wizard, so the one thing the family actually says out loud —
    a correction to what the bot wrote about a plant — was the one thing they could not do by saying it.
    nothing here may touch an interval or a care event: a wrong sentence is readable, a wrong interval is not.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.tools = PlantTools(
            uow_factory=self.uow_factory, settings=Settings(SENSOR_ROOMS='{"temp-room": "кухня-вітальня"}')
        )

    async def plant_field(self, plant_id: int, field: str):
        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(plant_id)
            return getattr(plant, field)

    async def test_update_plant_card_writes_the_species_and_reports_what_it_replaced(self):
        plant_id = await self.seed_plant(name="Принцеса", species="Medinilla magnifica")

        reported = await self.tools.run(
            "update_plant_card", {"plant": "Принцеса", "field": "species", "value": "Medinilla magnifica 'Lambada'"}
        )

        self.assertEqual(await self.plant_field(plant_id, "species"), "Medinilla magnifica 'Lambada'")
        self.assertEqual(
            reported,
            "Записав. Принцеса, вид: було «Medinilla magnifica», стало «Medinilla magnifica 'Lambada'».",
        )

    async def test_update_plant_card_with_a_null_value_clears_the_field_it_names(self):
        plant_id = await self.seed_plant(name="Принцеса", location="впритул до вікна")

        reported = await self.tools.run("update_plant_card", {"plant": "Принцеса", "field": "location", "value": None})

        self.assertIsNone(await self.plant_field(plant_id, "location"))
        self.assertEqual(reported, "Стер. Принцеса, місце: було «впритул до вікна», тепер порожньо.")

    async def test_update_plant_card_finds_the_plant_through_a_declined_name(self):
        plant_id = await self.seed_plant(name="Принцеса", species=None)

        reported = await self.tools.run(
            "update_plant_card", {"plant": "принцеси", "field": "species", "value": "Medinilla"}
        )

        self.assertEqual(await self.plant_field(plant_id, "species"), "Medinilla")
        self.assertEqual(reported, "Записав. Принцеса, вид: було порожньо, стало «Medinilla».")

    async def test_update_plant_card_with_a_name_two_plants_answer_to_asks_which_one(self):
        await self.seed_plant(name="Марті")
        await self.seed_plant(name="Мартін")

        reported = await self.tools.run("update_plant_card", {"plant": "мартіна", "field": "notes", "value": "полита"})

        self.assertEqual(reported, "«мартіна» підходить і до Марті, і до Мартін — уточни, про яку йдеться.")

    async def test_update_plant_card_with_an_unknown_name_lists_the_plants_there_are(self):
        await self.seed_plant(name="Принцеса")

        reported = await self.tools.run("update_plant_card", {"plant": "Фікус", "field": "notes", "value": "х"})

        self.assertEqual(reported, "Не знаходжу рослину «Фікус». Є: Принцеса.")

    async def test_update_plant_card_refuses_a_room_no_sensor_covers(self):
        plant_id = await self.seed_plant(name="Принцеса", room="кухня-вітальня")

        reported = await self.tools.run("update_plant_card", {"plant": "Принцеса", "field": "room", "value": "спальня"})

        self.assertEqual(await self.plant_field(plant_id, "room"), "кухня-вітальня")
        self.assertEqual(
            reported,
            "Кімнати «спальня» немає серед тих, де стоять датчики, а за ними цю рослину й судять. "
            "Є: кухня-вітальня.",
        )

    async def test_update_plant_card_refuses_a_field_that_would_move_a_reminder(self):
        plant_id = await self.seed_plant(name="Принцеса")

        reported = await self.tools.run(
            "update_plant_card", {"plant": "Принцеса", "field": "interval_days", "value": "3"}
        )

        self.assertEqual(await self.plant_field(plant_id, "name"), "Принцеса")
        self.assertEqual(reported, "Поле «interval_days» я не змінюю. Можу: вид, місце, кімната, нотатки.")

    async def test_update_plant_card_with_the_value_already_there_writes_nothing(self):
        await self.seed_plant(name="Принцеса", species="Medinilla magnifica")

        reported = await self.tools.run(
            "update_plant_card", {"plant": "Принцеса", "field": "species", "value": "Medinilla magnifica"}
        )

        self.assertEqual(reported, "Принцеса: тут уже саме це й записано, нічого не міняв.")

    async def test_update_plant_card_with_a_value_longer_than_the_column_refuses_it(self):
        plant_id = await self.seed_plant(name="Принцеса", species="Medinilla magnifica")

        reported = await self.tools.run(
            "update_plant_card", {"plant": "Принцеса", "field": "species", "value": "м" * 129}
        )

        self.assertEqual(await self.plant_field(plant_id, "species"), "Medinilla magnifica")
        self.assertEqual(reported, "Не записав: для поля «вид» цей текст задовгий.")

    async def test_set_plant_care_instructions_writes_the_instruction_for_the_task_it_names(self):
        plant_id = await self.seed_plant(name="Принцеса")
        await self.seed_care_schedule(plant_id, task_type=CareTaskType.WATERING, instructions="Лий зверху.")

        reported = await self.tools.run(
            "set_plant_care_instructions",
            {"plant": "Принцеси", "task_type": "watering", "instructions": "Лий знизу, у піддон."},
        )

        async with self.uow as uow:
            schedule = await uow.care_schedules.retrieve_for_plant(plant_id, CareTaskType.WATERING)
        self.assertEqual(schedule.instructions, "Лий знизу, у піддон.")
        self.assertEqual(reported, "Записав. Принцеса, полив: було «Лий зверху.», стало «Лий знизу, у піддон.».")

    async def test_set_plant_care_instructions_for_a_task_the_plant_does_not_have_says_so(self):
        plant_id = await self.seed_plant(name="Принцеса")
        await self.seed_care_schedule(plant_id, task_type=CareTaskType.WATERING)

        reported = await self.tools.run(
            "set_plant_care_instructions",
            {"plant": "Принцеса", "task_type": "repotting", "instructions": "Пересади навесні."},
        )

        self.assertEqual(reported, "Принцеса: немає завдання «пересадка», тож і інструкції до нього.")
