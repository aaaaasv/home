from datetime import timedelta

from src.bot.handlers.sensors import messages
from src.common.config import Settings
from src.tests.behaviour.base import BaseBehaviourTestCase, build_settings
from src.tests.telegram import CLIMATE_TOPIC, message_update

BEDROOM_SENSOR = "temp-bedroom"
KITCHEN_SENSOR = "temp-kitchen"
POT_SENSOR = "soil-probe"


class ClimateCommandTestCase(BaseBehaviourTestCase):
    """/climate driven through the real dispatcher, in the климат topic where it actually lives."""

    def build_settings_with_sensors(self, plant_id: int) -> Settings:
        base = build_settings().model_dump()
        base.update(
            SENSOR_ROOMS=f'{{"{BEDROOM_SENSOR}": "спальня", "{KITCHEN_SENSOR}": "кухня"}}',
            PLANT_SOIL_SENSORS=f'{{"{POT_SENSOR}": {plant_id}}}',
        )
        return Settings(**base)

    async def record(self, sensor: str, room: str | None, minutes_ago: int = 1, **values) -> None:
        async with self.uow as uow:
            await uow.sensor_readings.create(
                {
                    "sensor": sensor,
                    "room": room,
                    "measured_at": self.household_calendar.now() - timedelta(minutes=minutes_ago),
                    "temperature_celsius": values.get("temperature"),
                    "relative_humidity_percent": values.get("humidity"),
                    "soil_moisture_percent": values.get("soil"),
                    "battery_percent": values.get("battery"),
                }
            )

    async def ask(self, plant_id: int) -> str:
        await self.feed(
            message_update("/climate", topic=CLIMATE_TOPIC), settings=self.build_settings_with_sensors(plant_id)
        )
        return self.session.sent_texts()[-1]

    async def test_climate_shows_every_room_with_its_own_air(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.record(BEDROOM_SENSOR, "спальня", temperature=21.4, humidity=48)
        await self.record(KITCHEN_SENSOR, "кухня", temperature=23.6, humidity=52)

        text = await self.ask(plant_id)

        self.assertIn("· спальня — 21.4° · 48%", text)
        self.assertIn("· кухня — 23.6° · 52%", text)

    async def test_climate_averages_the_rooms_into_one_number(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.record(BEDROOM_SENSOR, "спальня", temperature=21.0, humidity=40)
        await self.record(KITCHEN_SENSOR, "кухня", temperature=23.0, humidity=50)

        text = await self.ask(plant_id)

        self.assertIn("загалом 22.0° · 45%", text)

    async def test_climate_names_a_pot_after_the_plant_standing_in_it(self):
        plant_id = await self.seed_plant(name="Містер Біг")
        await self.record(POT_SENSOR, None, temperature=19.4, soil=4)

        text = await self.ask(plant_id)

        self.assertIn("· Містер Біг — ґрунт 4% · 19°", text)

    async def test_climate_keeps_a_silent_room_visible_with_its_last_number_struck_through(self):
        """A room quietly missing from the list reads as a room that is fine."""
        plant_id = await self.seed_plant(name="Бубик")
        await self.record(BEDROOM_SENSOR, "спальня", minutes_ago=60 * 12, temperature=18.0, humidity=70)

        text = await self.ask(plant_id)

        self.assertIn("· спальня — <s>18.0° · 70%</s> <i>мовчить</i>", text)

    async def test_climate_warns_about_a_battery_that_is_nearly_out(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.record(BEDROOM_SENSOR, "спальня", temperature=21.0, humidity=40, battery=11)

        text = await self.ask(plant_id)

        self.assertIn("🔋 батарея 11%", text)

    async def test_climate_with_no_readings_at_all_says_so_rather_than_showing_an_empty_card(self):
        plant_id = await self.seed_plant(name="Бубик")

        text = await self.ask(plant_id)

        self.assertEqual(text, messages.CLIMATE_NOTHING_YET)

    async def test_climate_typed_outside_its_topic_points_back_to_the_group(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.record(BEDROOM_SENSOR, "спальня", temperature=21.0, humidity=40)

        await self.feed(message_update("/climate"), settings=self.build_settings_with_sensors(plant_id))

        self.assertNotIn("спальня", self.session.sent_texts()[-1])
