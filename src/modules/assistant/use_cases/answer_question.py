from collections.abc import Sequence
from datetime import datetime

from src.modules.assistant.services.conversation_memory import ConversationMemory
from src.modules.assistant.services.knowledge_source import KnowledgeSource
from src.modules.assistant.services.language_model import USER_ROLE, ConversationTurn, ImageAttachment, LanguageModel

# the household facts are the assistant's authority for questions about our home — transport, plants, devices — but
# everything else is open: it may use its own knowledge and a web search. it must not invent home-specific facts
# this is a model instruction, not a user message
GROUNDING_INSTRUCTION = (
    "Ти — домашній помічник родини. Відповідай коротко й українською. "
    "Нижче наведені факти про наш дім — покладайся на них, коли питання стосується нашого побуту "
    "(транспорт, рослини, пристрої тощо). Для решти вільно користуйся власними знаннями та пошуком в інтернеті. "
    "Не вигадуй фактів саме про наш дім, яких немає нижче — краще прямо скажи, що не знаєш. "
    "Це переписка в чаті: памʼятай попередні репліки розмови. "
    "З розмітки використовуй лише **жирний**, *курсив*, `код` і списки — без таблиць і заголовків."
)


class AnswerQuestionUseCase:
    """Grounds a question in the household facts and asks the model — provider-agnostic, the model is swappable"""

    def __init__(
        self,
        language_model: LanguageModel,
        knowledge_source: KnowledgeSource,
        conversation_memory: ConversationMemory,
    ):
        self.language_model = language_model
        self.knowledge_source = knowledge_source
        self.conversation_memory = conversation_memory

    async def __call__(
        self,
        question: str,
        conversation_id: int,
        asked_at: datetime,
        images: Sequence[ImageAttachment] = (),
        extra_facts: str | None = None,
    ) -> str | None:
        facts = await self.knowledge_source.gather()
        # a caller that knows more than the facts file — the plants topic knows this collection's own history —
        # adds it here rather than keeping a second model client of its own
        if extra_facts is not None:
            facts = f"{facts}\n\n{extra_facts}"

        # the facts belong in the system instruction, not in a turn: they are reread every time and would otherwise
        # pile up once per remembered question
        system_instruction = f"{GROUNDING_INSTRUCTION}\n\nФакти про дім:\n{facts}"
        conversation = [
            *self.conversation_memory.recall(conversation_id, asked_at),
            ConversationTurn(role=USER_ROLE, text=question, images=tuple(images)),
        ]

        answer = await self.language_model.generate(conversation, system_instruction)

        if answer is None:
            return None
        self.conversation_memory.remember(conversation_id, question, answer, asked_at)
        return answer
