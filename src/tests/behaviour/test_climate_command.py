from datetime import timedelta

from src.bot.handlers.sensors import messages
from src.common.config import Settings
from src.tests.behaviour.base import BaseBehaviourTestCase, build_settings
from src.tests.telegram import CHAT_ID, CLIMATE_TOPIC, callback_update, message_update

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

    async def test_climate_shows_the_temperature_range_of_the_last_day_under_each_room(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.record(BEDROOM_SENSOR, "спальня", minutes_ago=60 * 10, temperature=26.0, humidity=40)
        await self.record(BEDROOM_SENSOR, "спальня", minutes_ago=60 * 5, temperature=21.0, humidity=45)
        await self.record(BEDROOM_SENSOR, "спальня", temperature=23.2, humidity=43)

        text = await self.ask(plant_id)

        self.assertIn("· спальня — 23.2° · 43% (за добу 21–26°)", text)

    async def test_climate_leaves_out_the_range_when_the_day_was_flat(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.record(BEDROOM_SENSOR, "спальня", temperature=23.2, humidity=43)

        text = await self.ask(plant_id)

        self.assertNotIn("за добу", text)

    async def test_climate_says_how_many_plants_the_pot_probes_stand_for(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.seed_plant(name="Мімоза")
        await self.seed_plant(name="Кактус")
        await self.record(POT_SENSOR, None, temperature=19.4, soil=4)

        text = await self.ask(plant_id)

        self.assertIn("<b>Горщики</b> <i>(щупи у 1 з 3)</i>", text)

    async def test_climate_ends_with_a_time_the_client_renders_and_keeps_current(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.record(BEDROOM_SENSOR, "спальня", temperature=21.0, humidity=40)

        text = await self.ask(plant_id)

        self.assertTrue(text.endswith('<i><tg-time unix="1783836000" format="r">станом на 09:00</tg-time></i>'))

    async def test_climate_asked_twice_replaces_the_first_card_instead_of_adding_a_copy(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.record(BEDROOM_SENSOR, "спальня", temperature=21.0, humidity=40)
        settings = self.build_settings_with_sensors(plant_id)
        await self.feed(message_update("/climate", topic=CLIMATE_TOPIC), settings=settings)
        async with self.uow as uow:
            first_card = await uow.posted_messages.retrieve_latest_by_kind("climate_card", CHAT_ID)

        await self.feed(message_update("/climate", update_id=2, topic=CLIMATE_TOPIC), settings=settings)

        self.assertEqual(
            [call.message_thread_id for call in self.session.calls_named("SendMessage")], [CLIMATE_TOPIC, CLIMATE_TOPIC]
        )
        self.assertEqual(
            [call.message_id for call in self.session.calls_named("DeleteMessage")], [first_card.message_id]
        )

    async def test_climate_card_carries_a_refresh_button(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.record(BEDROOM_SENSOR, "спальня", temperature=21.0, humidity=40)

        await self.ask(plant_id)

        keyboard = self.session.calls_named("SendMessage")[-1].reply_markup.inline_keyboard
        self.assertEqual(
            [[(button.text, button.callback_data) for button in row] for row in keyboard],
            [[("🔄 Оновити", "climate_card:refresh")]],
        )

    async def test_climate_refresh_edits_the_pressed_card_with_the_new_numbers_and_sends_nothing(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.record(BEDROOM_SENSOR, "спальня", temperature=25.5, humidity=41)

        await self.feed(
            callback_update("climate_card:refresh", message_id=77), settings=self.build_settings_with_sensors(plant_id)
        )

        (edit,) = self.session.calls_named("EditMessageText")
        self.assertEqual(edit.message_id, 77)
        self.assertIn("· спальня — 25.5° · 41%", edit.text)
        self.assertEqual(self.session.calls_named("SendMessage"), [])
