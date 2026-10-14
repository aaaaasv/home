from src.bot.handlers.power.messages import POWER_SUPPLY_ON_STATION
from src.modules.power.domain import DeclaredSupply
from src.modules.power.use_cases.retrieve_declared_supply import RetrieveDeclaredSupplyUseCase
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.telegram import POWER_TOPIC, callback_update


class SupplyButtonsTestCase(BaseBehaviourTestCase):
    """
    The buttons under «світло є» that let a person say the hat is reading the station's own output.

    fed through the real dispatcher because that is the only thing that proves the handler's database and
    clock are actually injected — a parameter nothing supplies would leave the rest of the suite green.
    """

    async def declared(self) -> DeclaredSupply:
        return await RetrieveDeclaredSupplyUseCase(uow=self.uow_factory())()

    async def test_saying_the_station_feeds_the_socket_writes_it_down(self):
        await self.feed(callback_update("supply:station:0:0", topic=POWER_TOPIC))

        self.assertEqual(await self.declared(), DeclaredSupply.STATION)

    async def test_saying_the_station_feeds_the_socket_rewrites_the_card_that_asked(self):
        await self.feed(callback_update("supply:station:0:0", topic=POWER_TOPIC))

        edits = self.session.calls_named("EditMessageText")
        self.assertEqual([edit.text for edit in edits], [POWER_SUPPLY_ON_STATION])

    async def test_saying_it_is_the_grid_writes_that_down_too(self):
        await self.feed(callback_update("supply:station:0:0", topic=POWER_TOPIC))

        await self.feed(callback_update("supply:grid:0:0", topic=POWER_TOPIC))

        self.assertEqual(await self.declared(), DeclaredSupply.GRID)
