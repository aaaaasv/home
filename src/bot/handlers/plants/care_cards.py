"""The standing care card of each plant, kept in line with what is actually due."""
from collections.abc import Callable
from typing import NamedTuple

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.bot.formatting import exceeds_caption_limit
from src.bot.handlers.plants.care_card_reference import CareCardReference, parse_care_card_reference
from src.bot.handlers.plants.keyboards import CareCard, build_care_cards
from src.bot.message_cleanup import delete_message_quietly
from src.bot.services.posted_message_tracker import CARE_DIGEST_KIND
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.models import PostedMessage
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import CareDigest
from src.modules.plant_care.services.plant_air import PlantAir
from src.modules.plant_care.use_cases.build_care_digest import BuildCareDigestUseCase
from src.modules.plant_care.use_cases.retrieve_plant_card import RetrievePlantCardUseCase


class StandingCareCard(NamedTuple):
    posted: PostedMessage
    # None for a row an older version wrote, which no longer says what the card is about
    reference: CareCardReference | None


async def list_standing_care_cards(uow_factory: Callable[[], UnitOfWork]) -> list[StandingCareCard]:
    async with uow_factory() as uow:
        return [
            StandingCareCard(posted, parse_care_card_reference(posted.reference))
            for posted in await uow.posted_messages.list_by_kind(CARE_DIGEST_KIND)
        ]


async def read_probe_air_by_plant(
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    settings: Settings,
    plant_ids: set[int],
) -> dict[int, PlantAir]:
    """The pot's own reading for every plant that has a probe — a room's air is not the pot's, so it is left out."""
    probe_air_by_plant = {}
    for plant_id in sorted(plant_ids):
        card = await RetrievePlantCardUseCase(
            uow=uow_factory(), household_calendar=household_calendar, sensor_by_plant=settings.sensor_by_plant
        )(plant_id)
        if card.air is not None and card.air.room is None:
            probe_air_by_plant[plant_id] = card.air
    return probe_air_by_plant


async def build_care_cards_for_digest(
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    settings: Settings,
    digest: CareDigest,
) -> list[CareCard]:
    probe_air_by_plant = await read_probe_air_by_plant(
        uow_factory, household_calendar, settings, {task.plant_id for task in digest.tasks}
    )
    return build_care_cards(digest, probe_air_by_plant)


async def build_plant_care_card(
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    settings: Settings,
    plant_id: int,
) -> CareCard | None:
    """The card as it would be posted right now, or None once nothing is due for the plant."""
    digest = await BuildCareDigestUseCase(uow=uow_factory(), household_calendar=household_calendar)()
    plant_digest = CareDigest(today=digest.today, tasks=[task for task in digest.tasks if task.plant_id == plant_id])
    if not plant_digest.tasks:
        return None

    return (await build_care_cards_for_digest(uow_factory, household_calendar, settings, plant_digest))[0]


async def edit_care_card(bot: Bot, chat_id: int, message_id: int, card: CareCard) -> bool:
    """
    Rewrites a posted card in place. False when telegram will not, so the caller can post it afresh.

    an edit works however old the message is — the 48-hour limit is on deleting, and an edit was measured
    on the live bot at 49 days. what does fail is a card somebody deleted by hand.
    """
    # the tracker does not remember whether the card is a photo with a caption or plain text, so guess from the
    # data and try the other kind when telegram says the message is not that one
    prefers_caption = card.photo_file_id is not None and not exceeds_caption_limit(card.caption)
    for as_caption in (prefers_caption, not prefers_caption):
        try:
            if as_caption:
                await bot.edit_message_caption(
                    chat_id=chat_id, message_id=message_id, caption=card.caption, reply_markup=card.keyboard
                )
            else:
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id, text=card.caption, reply_markup=card.keyboard
                )
        except TelegramBadRequest as error:
            reason = str(error).lower()
            if "message is not modified" in reason:
                return True
            if "there is no" in reason:
                continue
            return False
        return True
    return False


async def retarget_care_card(uow_factory: Callable[[], UnitOfWork], message_id: int, reference: str) -> None:
    """Records what a tracked card now lists; a message the tracker never held, such as a /today card, is skipped."""
    async with uow_factory() as uow:
        for posted in await uow.posted_messages.list_by_kind(CARE_DIGEST_KIND):
            if posted.message_id == message_id and posted.reference != reference:
                await uow.posted_messages.update(posted.id, {"reference": reference})


async def forget_care_card(bot: Bot, uow_factory: Callable[[], UnitOfWork], posted: PostedMessage) -> None:
    await delete_message_quietly(bot, posted.chat_id, posted.message_id)
    async with uow_factory() as uow:
        await uow.posted_messages.delete(posted.id)


async def refresh_care_cards(
    bot: Bot,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
    settings: Settings,
    plant_id: int,
    except_message_id: int | None = None,
) -> None:
    """
    Brings a plant's standing cards in line after something settled one of its tasks, without ever posting.

    a card that lists what is still due is rewritten where it stands; one with nothing left to list is
    deleted, and so is one telegram will not let us edit — the next digest posts it again if it is still due.
    a settled card, a receipt with nothing due, is left for its owner: it is the only place a tap can be undone.
    """
    standing = [
        candidate
        for candidate in await list_standing_care_cards(uow_factory)
        if candidate.reference is not None
        and candidate.reference.plant_id == plant_id
        and candidate.reference.task_types
        and candidate.posted.message_id != except_message_id
    ]
    if not standing:
        return

    card = await build_plant_care_card(uow_factory, household_calendar, settings, plant_id)
    for candidate in standing:
        posted = candidate.posted
        if card is not None and await edit_care_card(bot, posted.chat_id, posted.message_id, card):
            await retarget_care_card(uow_factory, posted.message_id, card.reference)
        else:
            await forget_care_card(bot, uow_factory, posted)
