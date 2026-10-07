from datetime import datetime, timezone

from src.modules.plant_care.use_cases.gather_photos_for_question import GatherPhotosForQuestionUseCase
from src.tests.integration.base import BaseIntegrationTestCase


class GatherPhotosForQuestionTestCase(BaseIntegrationTestCase):
    """
    A typed question carries no image of its own, so the collection's own frames have to be found by name.

    without this the model was handed the written record alone and still answered as though it had looked at
    the pot.
    """

    async def gather(self, question: str):
        return await GatherPhotosForQuestionUseCase(uow=self.uow)(question)

    async def test_gather_for_a_question_naming_a_plant_returns_its_two_newest_frames(self):
        plant_id = await self.seed_plant(name="Бубик")
        for day, path in ((1, "/photos/one.jpg"), (5, "/photos/two.jpg"), (9, "/photos/three.jpg")):
            await self.seed_plant_photo(
                plant_id=plant_id,
                local_path=path,
                taken_at=datetime(2026, 7, day, 10, 0, tzinfo=timezone.utc),
            )

        gathered = await self.gather("що з листям Бубика?")

        self.assertEqual([photo.local_path for photo in gathered], ["/photos/two.jpg", "/photos/three.jpg"])
        self.assertEqual([photo.plant_name for photo in gathered], ["Бубик", "Бубик"])
        self.assertEqual(
            [photo.taken_at for photo in gathered],
            [datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc), datetime(2026, 7, 9, 10, 0, tzinfo=timezone.utc)],
        )

    async def test_gather_for_a_question_naming_no_plant_returns_nothing(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.seed_plant_photo(plant_id=plant_id, local_path="/photos/one.jpg")

        self.assertEqual(await self.gather("чому жовтіє листя?"), [])

    async def test_gather_ignores_a_plant_named_in_a_different_case(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.seed_plant_photo(plant_id=plant_id, local_path="/photos/one.jpg")

        gathered = await self.gather("ЩО З БУБИК?")

        self.assertEqual([photo.local_path for photo in gathered], ["/photos/one.jpg"])

    async def test_gather_skips_a_photo_that_was_never_stored_on_disk(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.seed_plant_photo(plant_id=plant_id, local_path=None, telegram_file_unique_id="unique-a")
        await self.seed_plant_photo(plant_id=plant_id, local_path="/photos/one.jpg", telegram_file_unique_id="unique-b")

        gathered = await self.gather("як Бубик?")

        self.assertEqual([photo.local_path for photo in gathered], ["/photos/one.jpg"])

    async def test_gather_for_a_question_naming_three_plants_stops_at_two(self):
        for name in ("Бубик", "Кроко", "Тігл"):
            plant_id = await self.seed_plant(name=name)
            await self.seed_plant_photo(plant_id=plant_id, local_path=f"/photos/{plant_id}.jpg")

        gathered = await self.gather("порівняй Бубик, Кроко і Тігл")

        self.assertEqual([photo.plant_name for photo in gathered], ["Бубик", "Кроко"])

    async def test_gather_for_an_archived_plant_returns_nothing(self):
        plant_id = await self.seed_plant(name="Бубик", is_archived=True)
        await self.seed_plant_photo(plant_id=plant_id, local_path="/photos/one.jpg")

        self.assertEqual(await self.gather("як Бубик?"), [])

    async def test_gather_for_an_empty_question_returns_nothing(self):
        await self.seed_plant(name="Бубик")

        self.assertEqual(await self.gather(""), [])
