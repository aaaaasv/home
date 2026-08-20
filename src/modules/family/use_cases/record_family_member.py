from src.common.use_case import BaseUseCase
from src.modules.family.domain import FamilyMember


class RecordFamilyMemberUseCase(BaseUseCase):
    """Remembers a household member the first time they write, and answers with what to call them."""

    async def __call__(self, telegram_user_id: int, display_name: str) -> FamilyMember:
        async with self.uow as uow:
            return FamilyMember.from_row(await uow.family_members.upsert(telegram_user_id, display_name))
