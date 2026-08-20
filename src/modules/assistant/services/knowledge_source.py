import asyncio
from pathlib import Path
from typing import Protocol


class KnowledgeSource(Protocol):
    """The household facts the assistant is allowed to answer from"""

    async def gather(self) -> str:
        ...


class FileKnowledgeSource:
    """Reads the curated home-knowledge file kept on the pi, so the facts can change without a redeploy"""

    def __init__(self, knowledge_path: Path):
        self.knowledge_path = knowledge_path

    async def gather(self) -> str:
        # off the event loop: this runs on every question, from an sd card
        return await asyncio.to_thread(self._read)

    def _read(self) -> str:
        if not self.knowledge_path.exists():
            return ""
        return self.knowledge_path.read_text(encoding="utf-8").strip()
