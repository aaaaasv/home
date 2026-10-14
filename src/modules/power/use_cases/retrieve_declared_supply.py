from src.common.use_case import BaseUseCase
from src.modules.power.domain import DeclaredSupply


class RetrieveDeclaredSupplyUseCase(BaseUseCase):
    """
    What the family last said is feeding the socket the hat measures, and the grid until they say otherwise.

    everything that turns the hat's reading into a word about the city asks this first — the announcement,
    the reserve board, the shortfall forecast and the heads-up about a planned outage — so it is one use case
    rather than the same two lines in four places.
    """

    async def __call__(self) -> DeclaredSupply:
        async with self.uow as uow:
            declared = await uow.supply_declaration.retrieve_current()
        return DeclaredSupply(declared.supply) if declared is not None else DeclaredSupply.GRID
