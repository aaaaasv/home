"""The scheduled jobs that post the care digest and watch the room climate."""
import logging
from collections.abc import Callable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.bot.formatting import exceeds_caption_limit
from src.bot.handlers.plants.formatting import render_plant_comfort_restored, render_plant_discomfort_card
from src.bot.handlers.plants.keyboards import build_care_cards
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import CARE_DIGEST_KIND, PLANT_DISCOMFORT_KIND, PostedMessageTracker
from src.common.config import Settings
from src.common.constants import ClimateComfortTransition
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import CareDigest, PlantComfortChange
from src.modules.plant_care.services.room_climate_sensor import RoomClimateSensor
from src.modules.plant_care.use_cases.deliver_daily_care_digest import DeliverDailyCareDigestUseCase
from src.modules.plant_care.use_cases.evaluate_plant_climate import EvaluatePlantClimateUseCase
from src.modules.plant_care.use_cases.retrieve_uncomfortable_plants import RetrieveUncomfortablePlantsUseCase

logger = logging.getLogger(__name__)


MISSING_TOPIC_ERROR = "message thread not found"


class DailyCareDigestJob:
    """
    Checks on an interval whether today's digest is due to go out, so a fixed daily time cannot lose it.

    if the pi is down at digest time, the first check after it boots delivers the reminder; the sent-date marker
    then keeps it to one digest per day.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        care_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        household_calendar: HouseholdCalendar,
        settings: Settings,
        posted_message_tracker: PostedMessageTracker,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.care_topic = care_topic
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar
        self.settings = settings
        self.posted_message_tracker = posted_message_tracker

    async def __call__(self) -> None:
        digest = await DeliverDailyCareDigestUseCase(
            uow=self.uow_factory(),
            household_calendar=self.household_calendar,
            digest_time=self.settings.daily_digest_time,
            weekend_digest_time=self.settings.weekend_digest_time,
        )()
        if digest is None:
            return

        topic_id = await self.care_topic.resolve()
        try:
            await self._send_digest(digest, topic_id)
        except TelegramBadRequest as error:
            # someone deleted the topic between two digests, so make a new one rather than lose the reminder
            if topic_id is None or MISSING_TOPIC_ERROR not in error.message.lower():
                raise
            logger.warning("Forum topic %s is gone, creating a new one", topic_id)
            await self._send_digest(digest, await self.care_topic.create())

        # record only after a successful send, so a send that fails is retried on the next check
        async with self.uow_factory() as uow:
            await uow.care_digest_deliveries.record_sent(digest.today)
        logger.info("Sent the digest for %s with %s tasks", digest.today, len(digest.tasks))

    async def _send_digest(self, digest: CareDigest, topic_id: int | None) -> None:
        # clear yesterday's leftover cards, then post one per plant so the family sees at a glance which needs what
        await self.posted_message_tracker.clear(CARE_DIGEST_KIND)
        # one push per digest, not one per plant — five plants due used to mean five buzzes
        for position, card in enumerate(build_care_cards(digest)):
            silent = position > 0
            if card.photo_file_id is None:
                sent = await self.bot.send_message(
                    chat_id=self.chat_id,
                    message_thread_id=topic_id,
                    text=card.caption,
                    reply_markup=card.keyboard,
                    # the daily "these plants need care today" push — the one message the whole system exists for
                    disable_notification=silent,
                )
            elif exceeds_caption_limit(card.caption):
                # the photo cannot carry this caption, so it goes bare and the text keeps the buttons
                await self.bot.send_photo(
                    chat_id=self.chat_id,
                    message_thread_id=topic_id,
                    photo=card.photo_file_id,
                    disable_notification=True,
                )
                sent = await self.bot.send_message(
                    chat_id=self.chat_id,
                    message_thread_id=topic_id,
                    text=card.caption,
                    reply_markup=card.keyboard,
                    disable_notification=silent,
                )
            else:
                sent = await self.bot.send_photo(
                    chat_id=self.chat_id,
                    message_thread_id=topic_id,
                    photo=card.photo_file_id,
                    caption=card.caption,
                    reply_markup=card.keyboard,
                    disable_notification=silent,
                )
            await self.posted_message_tracker.remember(CARE_DIGEST_KIND, sent, reference=card.task_reference)


class RoomClimateJob:
    """
    Samples the sensor every minute but speaks only when a plant CROSSES the line between comfortable and not.

    each uncomfortable plant gets one standing card. the card is deleted the moment the plant is comfortable
    again, and a short "знову комфортно" line takes its place, so the topic never keeps a complaint that is no
    longer true. a fresh crossing pings; a plant that is still uncomfortable but on different dimensions has its
    card rewritten silently — a bot that speaks every morning is a bot the family mutes, taking the digest with it.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        care_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        sensor: RoomClimateSensor,
        settings: Settings,
        posted_message_tracker: PostedMessageTracker,
        household_calendar: HouseholdCalendar,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.care_topic = care_topic
        self.uow_factory = uow_factory
        self.sensor = sensor
        self.settings = settings
        self.posted_message_tracker = posted_message_tracker
        self.household_calendar = household_calendar

    async def __call__(self) -> None:
        changes = await EvaluatePlantClimateUseCase(
            uow=self.uow_factory(),
            sensor=self.sensor,
            alert_window_hours=self.settings.CLIMATE_ALERT_WINDOW_HOURS,
            temperature_hysteresis_celsius=self.settings.CLIMATE_HYSTERESIS_TEMPERATURE_CELSIUS,
            humidity_hysteresis_percent=self.settings.CLIMATE_HYSTERESIS_HUMIDITY_PERCENT,
        )()
        if not changes:
            return

        topic_id = await self.care_topic.resolve()
        for change in changes:
            await self._deliver(change, topic_id)
        logger.info("Plant comfort changed for %s plant(s)", len(changes))

    async def _deliver(self, change: PlantComfortChange, topic_id: int | None) -> None:
        reference = str(change.plant_id)
        if change.transition == ClimateComfortTransition.BECAME_COMFORTABLE:
            await self.posted_message_tracker.clear_one(PLANT_DISCOMFORT_KIND, reference)
            await self.bot.send_message(
                chat_id=self.chat_id,
                message_thread_id=topic_id,
                text=render_plant_comfort_restored(change.plant_name),
                # good news, not a call to action — let it land without a ping
                disable_notification=True,
            )
            return

        text = render_plant_discomfort_card(change)
        if change.transition == ClimateComfortTransition.STILL_UNCOMFORTABLE and await self._edited_in_place(
            reference, text
        ):
            return

        # a fresh crossing (or a card that could not be edited) — post the plant its own card and remember it
        await self.posted_message_tracker.clear_one(PLANT_DISCOMFORT_KIND, reference)
        posted = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=topic_id,
            text=text,
            # a plant that just crossed out of range deserves a ping; a silent rewrite of a card already there does not
            disable_notification=change.transition == ClimateComfortTransition.STILL_UNCOMFORTABLE,
        )
        await self.posted_message_tracker.remember(PLANT_DISCOMFORT_KIND, posted, reference=reference)

    async def _edited_in_place(self, reference: str, text: str) -> bool:
        async with self.uow_factory() as uow:
            posted = await uow.posted_messages.list_by_reference(PLANT_DISCOMFORT_KIND, reference)
        if not posted:
            return False

        try:
            await self.bot.edit_message_text(chat_id=self.chat_id, message_id=posted[-1].message_id, text=text)
        except TelegramBadRequest as error:
            # unchanged text needs no rewrite; anything else (gone, older than 48h) falls back to a fresh card
            return "message is not modified" in str(error).lower()
        return True

    async def refresh_discomfort_cards(self) -> None:
        """
        Re-surface every still-uncomfortable plant's card at the bottom of the topic, silently, at most once a day.

        the edge path above pings once when a plant first crosses; but that standing card scrolls away, and the edge
        path never re-posts it because nothing changed. so the first run of a new day reposts it fresh (no ping — it
        already pinged), keeping the current discomfort visible, and cleans up a card whose plant has recovered.

        this job also fires on every boot, and a card already surfaced today is left exactly where it is: reposting
        the same complaint on each redeploy is the kind of noise that gets the whole topic muted.
        """
        uncomfortable = await RetrieveUncomfortablePlantsUseCase(
            uow=self.uow_factory(), alert_window_hours=self.settings.CLIMATE_ALERT_WINDOW_HOURS
        )()
        topic_id = await self.care_topic.resolve()

        async with self.uow_factory() as uow:
            posted_day_by_reference = {
                posted.reference: self.household_calendar.local_date(posted.created_at)
                for posted in await uow.posted_messages.list_by_kind(PLANT_DISCOMFORT_KIND)
            }

        today = self.household_calendar.today()
        live_references = set()
        reposted = 0
        for change in uncomfortable:
            reference = str(change.plant_id)
            live_references.add(reference)
            # a card already surfaced today stays put — only a new day (or a lost card) earns a fresh repost
            if posted_day_by_reference.get(reference) == today:
                continue
            await self.posted_message_tracker.clear_one(PLANT_DISCOMFORT_KIND, reference)
            posted = await self.bot.send_message(
                chat_id=self.chat_id,
                message_thread_id=topic_id,
                text=render_plant_discomfort_card(change),
                disable_notification=True,
            )
            await self.posted_message_tracker.remember(PLANT_DISCOMFORT_KIND, posted, reference=reference)
            reposted += 1

        # a card whose plant has quietly recovered (a recovery the edge path missed) — clean it up
        for stale_reference in posted_day_by_reference.keys() - live_references:
            await self.posted_message_tracker.clear_one(PLANT_DISCOMFORT_KIND, stale_reference)
        logger.info("Discomfort cards: %s reposted, %s standing", reposted, len(live_references))
