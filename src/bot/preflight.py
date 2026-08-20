import logging

from aiogram import Bot
from aiogram.exceptions import TelegramMigrateToChat

logger = logging.getLogger(__name__)


class ChatIsUnusableError(RuntimeError):
    """The configured group cannot host the modules, so refuse to start rather than sit there silently"""


async def verify_reminder_chat(bot: Bot, chat_id: int) -> None:
    # get_chat is useless for this: on a migrated id it quietly returns the stale basic-group record with
    # is_forum false. get_chat_member_count is the cheap call that actually reports the migration
    try:
        await bot.get_chat_member_count(chat_id)
    except TelegramMigrateToChat as migration:
        raise ChatIsUnusableError(
            f"Chat {chat_id} was upgraded to a supergroup and its id changed — enabling topics does this. "
            f"Set TELEGRAM_REMINDER_CHAT_ID={migration.migrate_to_chat_id} in .env, then "
            f"`docker compose up -d --force-recreate` (a plain restart does not reload .env)."
        ) from migration

    chat = await bot.get_chat(chat_id)
    if not chat.is_forum:
        raise ChatIsUnusableError(
            f"Chat {chat_id} ('{chat.title}') has no topics enabled, so every module would answer nothing. "
            f"Turn Topics on in the group settings."
        )

    logger.info("Reminder chat %s ('%s') is a forum", chat_id, chat.title)
