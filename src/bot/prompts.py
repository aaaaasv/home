from aiogram.types import ForceReply, Message, User


async def ask_for_text(message: Message, asker: User, text: str, placeholder: str) -> Message:
    """Post a prompt that opens the asker's input field with a hint, and nobody else's."""
    # selective force-reply reaches only a mentioned user or the sender of the replied-to message, and a button
    # tap has neither, so the asker is mentioned through an empty link that renders as nothing
    silent_mention = f'<a href="tg://user?id={asker.id}">​</a>'
    return await message.answer(
        silent_mention + text,
        reply_markup=ForceReply(selective=True, input_field_placeholder=placeholder),
        disable_notification=True,
    )
