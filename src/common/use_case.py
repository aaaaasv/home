from src.common.domain import Actor
from src.infrastructure.db.uow import UnitOfWork


class BaseUseCase:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow


class BaseActorUseCase(BaseUseCase):
    def __init__(self, uow: UnitOfWork, actor: Actor):
        super().__init__(uow)
        self.actor = actor
