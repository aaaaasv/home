from src.common.use_case import BaseUseCase
from src.modules.family.domain import FamilyMember


class ListFamilyMembersUseCase(BaseUseCase):
    async def __call__(self) -> list[FamilyMember]:
        async with self.uow as uow:
            return [FamilyMember.from_row(member) for member in await uow.family_members.list_all()]
