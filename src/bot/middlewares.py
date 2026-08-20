import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Chat, TelegramObject, User

from src.common.domain import Actor
from src.infrastructure.db.uow import UnitOfWork
from src.modules.family.use_cases.record_family_member import RecordFamilyMemberUseCase

logger = logging.getLogger(__name__)


class AllowedUsersMiddleware(BaseMiddleware):
    """The bot lives in a shared group — only the household may drive it"""

    def __init__(self, allowed_telegram_user_ids: frozenset[int]):
        self.allowed_telegram_user_ids = allowed_telegram_user_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None or user.id not in self.allowed_telegram_user_ids:
            self._log_rejection(user, data.get("event_chat"))
            return None

        data["actor"] = Actor(telegram_user_id=user.id, display_name=user.full_name)
        return await handler(event, data)

    def _log_rejection(self, user: User | None, chat: Chat | None) -> None:
        """The ids printed here are how an empty allowlist gets bootstrapped on first run."""
        logger.warning(
            "Ignored update — telegram_user_id=%s name=%s chat_id=%s",
            user.id if user else None,
            user.full_name if user else None,
            chat.id if chat else None,
        )


class FamilyRosterMiddleware(BaseMiddleware):
    """Records each allowed member who writes, so the roster that lets a chore be tagged «Марта» fills itself"""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]):
        self.uow_factory = uow_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        actor: Actor | None = data.get("actor")
        if actor is not None:
            member = await RecordFamilyMemberUseCase(uow=self.uow_factory())(actor.telegram_user_id, actor.display_name)
            # everything downstream denormalises the actor's name onto its records, so resolve the chosen
            # name here — otherwise history keeps whatever telegram happened to call them that day
            data["actor"] = Actor(telegram_user_id=actor.telegram_user_id, display_name=member.name)
        return await handler(event, data)
