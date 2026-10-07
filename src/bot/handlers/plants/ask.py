"""Plain text in the plants topic is a question about these plants, answered from their own record."""
import logging
from collections.abc import Callable

from aiogram import F, Router
from aiogram.types import Message

from src.bot.handlers.assistant.ask import answer_in_place
from src.bot.handlers.plants import messages
from src.bot.handlers.plants.facts import gather_facts
from src.bot.handlers.plants.photo_review_prompt import format_day
from src.bot.services.household_facts import FactsContext
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.adapters.image_encoding import read_image_bytes
from src.infrastructure.db.uow import UnitOfWork
from src.modules.assistant.services.language_model import ImageAttachment
from src.modules.assistant.use_cases.answer_question import AnswerQuestionUseCase
from src.modules.plant_care.domain import QuestionPhoto
from src.modules.plant_care.use_cases.gather_photos_for_question import GatherPhotosForQuestionUseCase

logger = logging.getLogger(__name__)

router = Router(name="plant_questions")


# registered after every flow and command in this package, so it only sees text no wizard was waiting for.
# commands are excluded, or a mistyped /lst here would be sent to a language model as a question
@router.message(F.text, ~F.text.startswith("/"))
async def answer_about_the_plants(
    message: Message,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    settings: Settings,
    answer_question: AnswerQuestionUseCase | None = None,
) -> None:
    """
    Answers from what actually happened to these plants, not from what the internet says about the species.

    the whole point is «чому жовтіє листя Тігла» getting an answer that knows Тігл was watered every four days
    in 30% air, so the collection's own record is handed over as facts alongside the household ones — and, when
    the question names a plant, that plant's own photos go with it.
    """
    if answer_question is None:
        return

    thinking = await message.answer(messages.PLANT_QUESTION_THINKING)
    facts = await gather_facts(
        FactsContext(household_calendar=household_calendar, uow_factory=uow_factory, settings=settings)
    )
    photos = await GatherPhotosForQuestionUseCase(uow=uow_factory())(message.text)
    images, attached = load_question_photos(photos)
    if attached:
        facts = f"{facts}\n\n{describe_attached_photos(attached, household_calendar)}"
    await answer_in_place(thinking, answer_question, message.text, images=images, extra_facts=facts)


def load_question_photos(photos: list[QuestionPhoto]) -> tuple[list[ImageAttachment], list[QuestionPhoto]]:
    """The frames that could actually be read, and which ones they were — a pruned file is not a failed answer."""
    images, attached = [], []
    for photo in photos:
        try:
            images.append(ImageAttachment(data=read_image_bytes(photo.local_path)))
        except OSError:
            logger.warning("Could not read the stored photo of '%s' at %s", photo.plant_name, photo.local_path)
            continue
        attached.append(photo)
    return images, attached


def describe_attached_photos(photos: list[QuestionPhoto], calendar: HouseholdCalendar) -> str:
    """The images arrive unlabelled, so the facts say which plant each one is and when it was taken."""
    lines = [messages.PLANT_QUESTION_PHOTO_NOTE]
    lines.extend(
        messages.PLANT_QUESTION_PHOTO_LINE.format(
            plant=photo.plant_name, day=format_day(calendar.local_date(photo.taken_at))
        )
        for photo in photos
    )
    return "\n".join(lines)
