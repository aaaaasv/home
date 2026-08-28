"""Plain text in the plants topic is a question about these plants, answered from their own record."""
from collections.abc import Callable

from aiogram import F, Router
from aiogram.types import Message

from src.bot.handlers.assistant.ask import answer_in_place
from src.bot.handlers.plants import messages
from src.bot.handlers.plants.question_facts import render_collection_facts
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.assistant.use_cases.answer_question import AnswerQuestionUseCase
from src.modules.plant_care.use_cases.list_plants import ListPlantsUseCase
from src.modules.plant_care.use_cases.retrieve_plant_sheet import RetrievePlantSheetUseCase

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
    plants = await ListPlantsUseCase(uow=uow_factory(), household_calendar=household_calendar)()
    sheets = [
        await RetrievePlantSheetUseCase(uow=uow_factory(), household_calendar=household_calendar)(str(plant.id))
        for plant in plants
    ]
    await answer_in_place(
        thinking,
        answer_question,
        message.text,
        extra_facts=render_collection_facts(sheets, household_calendar),
    )
