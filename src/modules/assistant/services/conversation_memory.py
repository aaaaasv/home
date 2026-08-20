from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.modules.assistant.services.language_model import MODEL_ROLE, USER_ROLE, ConversationTurn

# always even: turns are remembered in question/answer pairs, so an odd cap would drop an answer from its question
REMEMBERED_TURNS = 10
FORGET_AFTER = timedelta(minutes=30)


@dataclass
class RememberedConversation:
    turns: deque[ConversationTurn]
    spoke_last_at: datetime


class ConversationMemory:
    """
    The assistant's short-term memory: the last few turns of each topic, so "а коли наступний?" knows what came
    before. it lives in the process rather than the database — a restart is a fine moment to forget small talk,
    and an idle gap ends the conversation so a fresh question is not answered in yesterday's context
    """

    def __init__(self, remembered_turns: int = REMEMBERED_TURNS, forget_after: timedelta = FORGET_AFTER):
        self.remembered_turns = remembered_turns
        self.forget_after = forget_after
        self.conversations: dict[int, RememberedConversation] = {}

    def recall(self, conversation_id: int, now: datetime) -> list[ConversationTurn]:
        conversation = self.conversations.get(conversation_id)
        if conversation is None:
            return []
        if now - conversation.spoke_last_at > self.forget_after:
            del self.conversations[conversation_id]
            return []
        return list(conversation.turns)

    def remember(self, conversation_id: int, question: str, answer: str, answered_at: datetime) -> None:
        # images are deliberately left out: resending every photo with each follow-up would burn the free tier,
        # and the answer already says in words what was on it
        conversation = self.conversations.setdefault(
            conversation_id,
            RememberedConversation(turns=deque(maxlen=self.remembered_turns), spoke_last_at=answered_at),
        )
        conversation.turns.append(ConversationTurn(role=USER_ROLE, text=question))
        conversation.turns.append(ConversationTurn(role=MODEL_ROLE, text=answer))
        conversation.spoke_last_at = answered_at
