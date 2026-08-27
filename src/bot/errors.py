import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from src.bot import messages
from src.common.constants import ErrorCode
from src.common.exceptions import DomainError

logger = logging.getLogger(__name__)

router = Router(name="errors")

ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.NOT_FOUND: messages.NOT_FOUND,
    ErrorCode.ALREADY_EXISTS: messages.ALREADY_EXISTS,
    ErrorCode.CONFLICT: messages.CONFLICT,
    ErrorCode.VALIDATION_ERROR: messages.INVALID_INPUT,
}


@router.errors()
async def reply_with_error(event: ErrorEvent) -> bool:
    message = _resolve_message(event.exception)
    logger.exception("Update %s failed", event.update.update_id, exc_info=event.exception)

    if event.update.callback_query is not None:
        await event.update.callback_query.answer(message, show_alert=True)
        return True
    if event.update.message is not None:
        await event.update.message.answer(message)
        return True
    return True


def _resolve_message(exception: Exception) -> str:
    if isinstance(exception, DomainError):
        return ERROR_MESSAGES.get(exception.code, messages.UNEXPECTED_ERROR)
    return messages.UNEXPECTED_ERROR
