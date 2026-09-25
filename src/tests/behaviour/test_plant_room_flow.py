import json

from src.bot.handlers.plants import messages
from src.common.config import Settings
from src.tests.behaviour.base import BaseBehaviourTestCase, build_settings
from src.tests.telegram import callback_update, message_update

BEDROOM = "спальня"
LIVING_ROOM = "кухня-вітальня"


def settings_with_rooms(**overrides) -> Settings:
    return build_settings().model_copy(
        update={"SENSOR_ROOMS": json.dumps({"temp-bedroom": BEDROOM, "temp-living": LIVING_ROOM}), **overrides}
    )


class PlantRoomFlowTestCase(BaseBehaviourTestCase):
    """
    Setting a plant's room, driven the way a person drives it.

    the room decides which air the plant is judged by, so a typo that silently stores an unknown room would
    put the plant back where it started — invisible and unjudged. the flow refuses one instead.
    """

    async def seed_plant_to_edit(self) -> int:
        return await self.seed_plant(name="Монстера")

    async def open_the_room_prompt(self, plant_id: int, settings: Settings, update_id: int = 1) -> None:
        await self.feed(
            callback_update(f"edit_plant:{plant_id}:room", update_id=update_id),
            settings=settings,
        )

    async def test_the_room_prompt_lists_the_rooms_a_sensor_actually_covers(self):
        plant_id = await self.seed_plant_to_edit()

        await self.open_the_room_prompt(plant_id, settings_with_rooms())

        self.assertEqual(
            self.session.sent_texts()[-1],
            messages.EDIT_FIELD_PROMPTS["room"].format(rooms=f"{LIVING_ROOM}, {BEDROOM}"),
        )

    async def test_the_room_prompt_says_so_when_no_room_has_a_sensor(self):
        plant_id = await self.seed_plant_to_edit()

        await self.open_the_room_prompt(plant_id, build_settings())

        self.assertEqual(self.session.sent_texts()[-1], messages.NO_ROOMS_HAVE_SENSORS)

    async def test_naming_a_room_that_has_a_sensor_stores_it(self):
        plant_id = await self.seed_plant_to_edit()
        settings = settings_with_rooms()
        await self.open_the_room_prompt(plant_id, settings)

        await self.feed(message_update(BEDROOM, update_id=2), settings=settings)

        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(plant_id)
        self.assertEqual(plant.room, BEDROOM)

    async def test_naming_a_room_in_any_capitalisation_stores_the_spelling_the_sensors_use(self):
        plant_id = await self.seed_plant_to_edit()
        settings = settings_with_rooms()
        await self.open_the_room_prompt(plant_id, settings)

        await self.feed(message_update("  Спальня ", update_id=2), settings=settings)

        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(plant_id)
        self.assertEqual(plant.room, BEDROOM)

    async def test_naming_a_room_with_no_sensor_is_refused_and_the_rooms_are_named(self):
        plant_id = await self.seed_plant_to_edit()
        settings = settings_with_rooms()
        await self.open_the_room_prompt(plant_id, settings)

        await self.feed(message_update("балкон", update_id=2), settings=settings)

        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(plant_id)
        self.assertEqual(plant.room, None)
        self.assertEqual(
            self.session.sent_texts()[-1],
            messages.ROOM_HAS_NO_SENSOR.format(room="балкон", rooms=f"{LIVING_ROOM}, {BEDROOM}"),
        )

    async def test_a_refused_room_leaves_the_flow_open_so_the_next_answer_still_lands(self):
        plant_id = await self.seed_plant_to_edit()
        settings = settings_with_rooms()
        await self.open_the_room_prompt(plant_id, settings)
        await self.feed(message_update("балкон", update_id=2), settings=settings)

        await self.feed(message_update(LIVING_ROOM, update_id=3), settings=settings)

        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(plant_id)
        self.assertEqual(plant.room, LIVING_ROOM)
