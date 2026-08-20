from typing import Protocol


class PhotoStorage(Protocol):
    """Keeps a local copy of a telegram photo so the journal survives the bot token"""

    async def save(self, telegram_file_id: str, telegram_file_unique_id: str) -> str | None:
        ...


class NullPhotoStorage:
    async def save(self, telegram_file_id: str, telegram_file_unique_id: str) -> str | None:
        return None
