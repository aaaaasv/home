from datetime import timedelta

from src.common.domain import Actor
from src.modules.places.commands import AddPlaceCommand, MarkPlaceVisitedCommand, RemovePlaceCommand, RenamePlaceCommand
from src.modules.places.use_cases.add_place import AddPlaceUseCase
from src.modules.places.use_cases.mark_place_visited import MarkPlaceVisitedUseCase
from src.modules.places.use_cases.remove_place import RemovePlaceUseCase
from src.modules.places.use_cases.rename_place import RenamePlaceUseCase
from src.modules.places.use_cases.retrieve_places import RetrievePlacesUseCase
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase

MARTA = Actor(telegram_user_id=1, display_name="Марта")
BOHDAN = Actor(telegram_user_id=2, display_name="Богдан")


class PlacesTestCase(BaseIntegrationTestCase):
    def add(self, actor: Actor = MARTA) -> AddPlaceUseCase:
        return AddPlaceUseCase(uow=self.uow, actor=actor)

    async def test_add_place_puts_it_in_the_to_visit_list_with_the_name_of_whoever_added(self):
        places = await self.add()(AddPlaceCommand(name="Кафе"))

        self.assertEqual([place.name for place in places.to_visit], ["Кафе"])
        self.assertEqual(places.to_visit[0].added_by_display_name, "Марта")
        self.assertEqual(places.visited, [])

    async def test_add_place_keeps_the_link_when_one_is_given(self):
        places = await self.add()(AddPlaceCommand(name="Кафе", link="https://maps.app.goo.gl/abc"))

        self.assertEqual(places.to_visit[0].link, "https://maps.app.goo.gl/abc")

    async def test_add_place_that_is_already_on_the_list_does_not_duplicate_it(self):
        await self.add()(AddPlaceCommand(name="Кафе"))

        places = await self.add(BOHDAN)(AddPlaceCommand(name="кафе"))

        self.assertEqual(len(places.to_visit), 1)
        self.assertEqual(places.to_visit[0].added_by_display_name, "Марта")

    async def test_mark_place_visited_moves_it_into_the_history_with_who_and_when(self):
        await self.add()(AddPlaceCommand(name="Кафе"))
        place_id = (await RetrievePlacesUseCase(uow=self.uow)()).to_visit[0].id

        places = await MarkPlaceVisitedUseCase(uow=self.uow, actor=BOHDAN, visited_at=FROZEN_NOW)(
            MarkPlaceVisitedCommand(place_id=place_id)
        )

        self.assertEqual(places.to_visit, [])
        self.assertEqual([place.name for place in places.visited], ["Кафе"])
        self.assertEqual(places.visited[0].visited_by_display_name, "Богдан")
        self.assertEqual(places.visited[0].visited_at, FROZEN_NOW)

    async def test_retrieve_places_orders_the_history_newest_visit_first(self):
        await self.add()(AddPlaceCommand(name="Перше"))
        await self.add()(AddPlaceCommand(name="Друге"))
        first_id, second_id = (place.id for place in (await RetrievePlacesUseCase(uow=self.uow)()).to_visit)
        await MarkPlaceVisitedUseCase(uow=self.uow, actor=MARTA, visited_at=FROZEN_NOW)(
            MarkPlaceVisitedCommand(place_id=first_id)
        )
        await MarkPlaceVisitedUseCase(uow=self.uow, actor=MARTA, visited_at=FROZEN_NOW + timedelta(days=1))(
            MarkPlaceVisitedCommand(place_id=second_id)
        )

        places = await RetrievePlacesUseCase(uow=self.uow)()

        self.assertEqual([place.name for place in places.visited], ["Друге", "Перше"])

    async def test_rename_place_fixes_the_name(self):
        await self.add()(AddPlaceCommand(name="кафе"))
        place_id = (await RetrievePlacesUseCase(uow=self.uow)()).to_visit[0].id

        places = await RenamePlaceUseCase(uow=self.uow)(RenamePlaceCommand(place_id=place_id, name="Кафе"))

        self.assertEqual([place.name for place in places.to_visit], ["Кафе"])

    async def test_remove_place_drops_it_entirely(self):
        await self.add()(AddPlaceCommand(name="Помилка"))
        place_id = (await RetrievePlacesUseCase(uow=self.uow)()).to_visit[0].id

        places = await RemovePlaceUseCase(uow=self.uow)(RemovePlaceCommand(place_id=place_id))

        self.assertTrue(places.is_empty)
