from src.common.use_case import BaseUseCase


class RecordFamilyMemberUseCase(BaseUseCase):
    """Remembers a household member the first time they write, so a chore can be tagged to them by name later"""

    async def __call__(self, telegram_user_id: int, display_name: str) -> None:
        async with self.uow as uow:
            await uow.family_members.upsert(telegram_user_id, display_name)
