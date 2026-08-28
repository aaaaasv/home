"""A telegram that never leaves the process, so a handler can be driven the way an update drives it in the flat."""
import time
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User

TOKEN = "8000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
CHAT_ID = -1002000000000
# one topic per module, because the topic is what tells one module's /add from another's
PLANTS_TOPIC = 7
SHOPPING_TOPIC = 8
PLACES_TOPIC = 9
CHORES_TOPIC = 10
ACTOR_ID = 900000001
ACTOR_NAME = "Тест"


class RecordingSession(BaseSession):
    """
    Answers every api call from memory and keeps the call itself, which is the whole point.

    what a handler *did* is exactly the list of methods it asked telegram to run, so the assertions read as
    "it sent this, then edited that" rather than reaching into the handler's own variables.
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self.next_message_id = 1000

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None) -> Any:
        self.calls.append(method)
        returning = method.__returning__
        if returning is Message or (isinstance(returning, type) and issubclass(returning, Message)):
            self.next_message_id += 1
            # bound to the bot, or the handler that later edits or deletes its own prompt finds no bot on it
            return build_message(
                text=getattr(method, "text", None) or getattr(method, "caption", "") or "",
                message_id=self.next_message_id,
                from_bot=True,
            ).as_(bot)
        # everything else the handlers call — answerCallbackQuery, deleteMessage, editMessageText on a caption —
        # replies with a bare True, which is what the real api sends back
        return True

    async def stream_content(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - never downloaded here
        raise NotImplementedError

    async def close(self) -> None:
        return None

    def sent_texts(self) -> list[str]:
        return [call.text for call in self.calls if getattr(call, "text", None) is not None]

    def calls_named(self, name: str) -> list[TelegramMethod]:
        return [call for call in self.calls if type(call).__name__ == name]


def build_bot(session: RecordingSession) -> Bot:
    return Bot(token=TOKEN, session=session)


def build_message(text: str, message_id: int = 1, from_bot: bool = False, topic: int = PLANTS_TOPIC) -> Message:
    return Message(
        message_id=message_id,
        date=time.time(),
        chat=Chat(id=CHAT_ID, type="supergroup"),
        message_thread_id=topic,
        from_user=User(id=ACTOR_ID, is_bot=from_bot, first_name=ACTOR_NAME),
        text=text,
    )


def message_update(text: str, update_id: int = 1, topic: int = PLANTS_TOPIC) -> Update:
    return Update(update_id=update_id, message=build_message(text, message_id=update_id, topic=topic))


def callback_update(data: str, update_id: int = 1, message_id: int = 1) -> Update:
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=str(update_id),
            from_user=User(id=ACTOR_ID, is_bot=False, first_name=ACTOR_NAME),
            chat_instance="test",
            data=data,
            message=build_message("", message_id=message_id, from_bot=True),
        ),
    )
