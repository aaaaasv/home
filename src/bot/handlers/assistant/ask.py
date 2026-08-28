from collections.abc import Sequence

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from src.bot.handlers.assistant import messages
from src.bot.markdown import render_markdown_as_html
from src.common.time import current_time
from src.modules.assistant.services.language_model import ImageAttachment, QuotaExhausted
from src.modules.assistant.use_cases.answer_question import AnswerQuestionUseCase

router = Router(name="assistant_ask")


@router.message(F.text & ~F.text.startswith("/"))
async def answer_a_question(message: Message, answer_question: AnswerQuestionUseCase) -> None:
    # plain text in this topic is a question; a leading "/" is a command for start.router or wrong_topic to claim
    thinking = await message.answer(messages.ASSISTANT_THINKING)
    await answer_in_place(thinking, answer_question, message.text)


@router.message(F.photo)
async def answer_about_a_photo(message: Message, answer_question: AnswerQuestionUseCase) -> None:
    # the caption is the question; a bare photo just asks what is on it
    thinking = await message.answer(messages.ASSISTANT_THINKING)
    downloaded_photo = await message.bot.download(message.photo[-1])
    await answer_in_place(
        thinking,
        answer_question,
        message.caption or messages.ASSISTANT_DESCRIBE_PHOTO,
        images=[ImageAttachment(data=downloaded_photo.read())],
    )


async def answer_in_place(
    thinking: Message,
    answer_question: AnswerQuestionUseCase,
    question: str,
    images: Sequence[ImageAttachment] = (),
    extra_facts: str | None = None,
) -> None:
    """The "думаю" placeholder turns into the answer — so a spent quota has to land there too, not in a new message"""
    try:
        # the placeholder sits in the topic the question was asked in, and that topic is the conversation
        answer = await answer_question(
            question,
            conversation_id=thinking.message_thread_id,
            asked_at=current_time(),
            images=images,
            extra_facts=extra_facts,
        )
    except QuotaExhausted as exhausted:
        limit_reached = (
            messages.ASSISTANT_DAILY_LIMIT_SPENT if exhausted.is_daily else messages.ASSISTANT_TOO_MANY_AT_ONCE
        )
        await thinking.edit_text(limit_reached)
        return
    await show_answer(thinking, answer)


async def show_answer(thinking: Message, answer: str | None) -> None:
    """The answer comes from a model, so telegram may still refuse to parse it — showing it raw beats losing it"""
    if answer is None:
        await thinking.edit_text(messages.ASSISTANT_UNAVAILABLE)
        return

    try:
        await thinking.edit_text(render_markdown_as_html(answer))
    except TelegramBadRequest:
        await thinking.edit_text(answer, parse_mode=None)
