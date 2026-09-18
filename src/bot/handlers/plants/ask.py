"""Plain text in the plants topic is a question about these plants, answered from their own record."""
from collections.abc import Callable

from aiogram import F, Router
from aiogram.types import Message

from src.bot.handlers.assistant.ask import answer_in_place
from src.bot.handlers.plants import messages
from src.bot.handlers.plants.facts import gather_facts
from src.bot.services.household_facts import FactsContext
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.assistant.use_cases.answer_question import AnswerQuestionUseCase

router = Router(name="plant_questions")


# registered after every flow and command in this package, so it only sees text no wizard was waiting for.
# commands are excluded, or a mistyped /lst here would be sent to a language model as a question
@router.message(F.text, ~F.text.startswith("/"))
async def answer_about_the_plants(
    message: Message,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    answer_question: AnswerQuestionUseCase | None = None,
) -> None:
    """
    Answers from what actually happened to these plants, not from what the internet says about the species.

    the whole point is «чому жовтіє листя Тігла» getting an answer that knows Тігл was watered every four days
    in 30% air, so the collection's own record is handed over as facts alongside the household ones.
    """
    if answer_question is None:
        return

    thinking = await message.answer(messages.PLANT_QUESTION_THINKING)
    facts = await gather_facts(FactsContext(household_calendar=household_calendar, uow_factory=uow_factory))
    await answer_in_place(thinking, answer_question, message.text, extra_facts=facts)
