from src.common.use_case import BaseUseCase


class RecordAirThreatMessageUseCase(BaseUseCase):
    """
    Remembers which message stands for which track, and what it currently says.

    the text is kept so the job can edit only when something actually changed: a track updates its position
    every few seconds, and rewriting an identical card that often would spend the edit budget on nothing.
    """

    async def __call__(self, tracker_id: str, chat_id: int, message_id: int, rendered_text: str) -> None:
        async with self.uow as uow:
            await uow.air_threat_notices.attach_message(tracker_id, chat_id, message_id, rendered_text)
