from collections.abc import Callable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from src.common.constants import CareTaskType
from src.infrastructure.db.uow import UnitOfWork

CARE_DIGEST_KIND = "care_digest"
AIR_CONDITIONER_CARD_KIND = "ac_card"
ECOFLOW_CARD_KIND = "ecoflow_card"
# the self-editing daily outage-schedule digest, plus the two lanes its pushes dedupe through
OUTAGE_SCHEDULE_KIND = "outage_schedule"
OUTAGE_PING_KIND = "outage_ping"
OUTAGE_EMERGENCY_KIND = "outage_emergency"
# one standing card for the shelved station's storage regime, deleted the moment it goes back into use
CONSERVATION_CARD_KIND = "conservation_card"
WEATHER_DIGEST_KIND = "weather_digest"
# one standing card per uncomfortable plant, referenced by plant id, deleted the moment the plant is comfortable
PLANT_DISCOMFORT_KIND = "plant_discomfort"
# one standing card per chore near its deadline, referenced by chore id, deleted the moment the chore is done
CHORE_DEADLINE_KIND = "chore_deadline"
# the on-demand transit arrival card — replaced on every /транспорт, so only the newest one is live
TRANSIT_CARD_KIND = "transit_card"
# the three self-editing list boards — one row each, replacing the per-module tables they used to own
SHOPPING_LIST_KIND = "shopping_list"
PLACES_LIST_KIND = "places_list"
CHORES_LIST_KIND = "chores_list"


def build_care_task_reference(plant_id: int, task_type: CareTaskType) -> str:
    """Names the one task a digest card is about, so that card can be dropped without touching the others"""
    return f"{task_type}:{plant_id}"


class PostedMessageTracker:
    """
    Remembers messages the bot posted so it can delete them once they go stale, one lane per kind.

    the daily care digest and the /ac card both replace themselves: clear() removes the previous batch, then each
    fresh message is remembered — so yesterday's reminder cards and last time's control panel do not pile up.
    a single card can also go stale on its own, once its task is done; clear_one() drops just that one.
    """

    def __init__(self, bot: Bot, uow_factory: Callable[[], UnitOfWork]):
        self.bot = bot
        self.uow_factory = uow_factory

    async def clear(self, kind: str) -> None:
        async with self.uow_factory() as uow:
            for posted in await uow.posted_messages.list_by_kind(kind):
                await self._delete_quietly(posted.chat_id, posted.message_id)
            await uow.posted_messages.delete_by_kind(kind)

    async def clear_one(self, kind: str, reference: str, keep_message_id: int | None = None) -> None:
        async with self.uow_factory() as uow:
            for posted in await uow.posted_messages.list_by_reference(kind, reference):
                if posted.message_id == keep_message_id:
                    # the caller rewrote this one in place, so it stays tracked until the next batch sweeps it
                    continue
                await self._delete_quietly(posted.chat_id, posted.message_id)
            await uow.posted_messages.delete_by_reference(kind, reference, keep_message_id=keep_message_id)

    async def remember(self, kind: str, message: Message, reference: str | None = None) -> None:
        async with self.uow_factory() as uow:
            await uow.posted_messages.create(
                {
                    "kind": kind,
                    "chat_id": message.chat.id,
                    "message_id": message.message_id,
                    "reference": reference,
                }
            )

    async def _delete_quietly(self, chat_id: int, message_id: int) -> None:
        try:
            await self.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramBadRequest:
            # already gone (someone recorded the care) or older than 48h — nothing to clean up
            pass
