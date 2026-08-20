from src.common.use_case import BaseUseCase
from src.modules.chores.domain import ChoresList


class RetrieveChoresUseCase(BaseUseCase):
    async def __call__(self) -> ChoresList:
        async with self.uow as uow:
            return ChoresList.from_chores(await uow.chores.list_all())
