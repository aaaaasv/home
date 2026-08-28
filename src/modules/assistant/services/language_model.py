from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

USER_ROLE = "user"
MODEL_ROLE = "model"


class QuotaExhausted(Exception):
    """
    The free tier said no more — a spent day and a busy minute both arrive as 429, so they are told apart here
    and the caller can promise the right thing: tomorrow morning, or a minute from now
    """

    def __init__(self, is_daily: bool):
        self.is_daily = is_daily
        super().__init__("The daily free-tier quota is spent" if is_daily else "The per-minute quota is spent")


@dataclass(frozen=True)
class ImageAttachment:
    """Raw image bytes plus their mime type, ready to inline into a multimodal request"""

    data: bytes
    mime_type: str = "image/jpeg"


@dataclass(frozen=True)
class ConversationTurn:
    """One message of the running conversation — either the family's question or the model's own answer"""

    role: str
    text: str
    images: Sequence[ImageAttachment] = field(default_factory=tuple)


class LanguageModel(Protocol):
    """
    Answers the last turn of a conversation — returns None when the model cannot be reached, and raises
    QuotaExhausted when it could be reached but refused, which is a different thing to tell the family
    """

    async def generate(self, conversation: Sequence[ConversationTurn], system_instruction: str) -> str | None:
        ...
