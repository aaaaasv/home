from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from src.bot.services.forum_topic_registry import ForumTopicRegistry


class InModuleTopic(BaseFilter):
    """A module answers commands only inside its own forum topic, so /add in the shopping topic stays shopping"""

    def __init__(self, forum_topic: ForumTopicRegistry):
        self.forum_topic = forum_topic

    async def __call__(self, message: Message) -> bool:
        # an unresolved topic must reject, not wave everything through: two modules would both claim /add
        if self.forum_topic.topic_id is None:
            return False

        # private chats and the General topic both carry no thread id, so neither can name a module
        return message.message_thread_id == self.forum_topic.topic_id


class HasAccessibleMessage(BaseFilter):
    """
    Buttons are not filtered by topic — a callback names its module in its own payload prefix, and filtering by
    topic would break every button the bot posts outside its topic. it only has to survive telegram replacing the
    message of an unreachable callback with an InaccessibleMessage, which carries no thread id and cannot be edited
    """

    async def __call__(self, callback: CallbackQuery) -> bool:
        return isinstance(callback.message, Message)
