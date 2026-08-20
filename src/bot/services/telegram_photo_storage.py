import logging
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


class TelegramPhotoStorage:
    def __init__(self, bot: Bot, storage_path: Path):
        self.bot = bot
        self.storage_path = storage_path

    async def save(self, telegram_file_id: str, telegram_file_unique_id: str) -> str | None:
        destination = self.storage_path / f"{telegram_file_unique_id}.jpg"
        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)
            await self.bot.download(telegram_file_id, destination=destination)
        except (TelegramAPIError, OSError):
            logger.exception("Failed to store a local copy of telegram photo %s", telegram_file_id)
            return None
        return str(destination)
