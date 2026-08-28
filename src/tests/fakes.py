from collections.abc import Sequence
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from aiogram.types import Chat
from aiogram.types import ForumTopic as TelegramForumTopic

from src.common.household_calendar import HouseholdCalendar
from src.modules.assistant.services.language_model import ConversationTurn, QuotaExhausted
from src.modules.plant_care.domain import PlantPhotoReview, PlantPhotoReviewContext
from src.modules.room_climate.domain import RoomClimate
from src.modules.shopping.domain import TrackedProduct
from src.modules.transit.domain import RealtimeSnapshot, RouteShape


class FrozenHouseholdCalendar(HouseholdCalendar):
    def __init__(self, timezone: ZoneInfo, frozen_now: datetime):
        super().__init__(timezone)
        self.frozen_now = frozen_now

    def now(self) -> datetime:
        return self.frozen_now


class FakeForumBot:
    def __init__(self, is_forum: bool = True, first_message_thread_id: int = 100):
        self.is_forum = is_forum
        self.next_message_thread_id = first_message_thread_id
        self.created_topic_names: list[str] = []

    async def get_chat(self, chat_id: int) -> Chat:
        return Chat(id=chat_id, type="supergroup", is_forum=self.is_forum)

    async def create_forum_topic(self, chat_id: int, name: str) -> TelegramForumTopic:
        self.created_topic_names.append(name)
        topic = TelegramForumTopic(message_thread_id=self.next_message_thread_id, name=name, icon_color=0)
        self.next_message_thread_id += 1
        return topic


class FixedRoomClimateSensor:
    def __init__(self, climate: RoomClimate | None):
        self.climate = climate

    async def read(self) -> RoomClimate | None:
        return self.climate


class StubForumTopic:
    """A resolved topic that just hands back its thread id, standing in for a ForumTopicRegistry in job tests"""

    def __init__(self, thread_id: int = 100):
        self.thread_id = thread_id

    @property
    def topic_id(self) -> int:
        return self.thread_id

    async def resolve(self) -> int:
        return self.thread_id


class RecordingBot:
    """Records the messages a scheduled job sends, edits and deletes, and hands back an id the tracker can remember"""

    def __init__(self, first_message_id: int = 500):
        self.next_message_id = first_message_id
        self.sent: list[dict] = []
        self.edited: list[dict] = []
        self.deleted: list[int] = []

    async def send_message(
        self, chat_id, message_thread_id=None, text=None, reply_markup=None, disable_notification=False
    ):
        message_id = self.next_message_id
        self.next_message_id += 1
        self.sent.append(
            {
                "message_id": message_id,
                "chat_id": chat_id,
                "message_thread_id": message_thread_id,
                "text": text,
                "silent": disable_notification,
            }
        )
        return SimpleNamespace(message_id=message_id, chat=SimpleNamespace(id=chat_id))

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edited.append({"chat_id": chat_id, "message_id": message_id, "text": text})

    async def delete_message(self, chat_id, message_id):
        self.deleted.append(message_id)


class RecordingPhotoAnalyst:
    def __init__(self, review: PlantPhotoReview | None = None):
        self.review = review
        self.reviewed_contexts: list[PlantPhotoReviewContext] = []

    async def review_photo(self, context: PlantPhotoReviewContext) -> PlantPhotoReview | None:
        self.reviewed_contexts.append(context)
        return self.review


class ScriptedPriceSource:
    """Returns a queued price per fetched url; a None in the queue models a page that could not be read"""

    def __init__(
        self,
        prices_by_url: dict[str, list[int | None]],
        name: str = "Тестовий товар",
        shop: str | None = None,
        rating: int | None = None,
        buy_link: str | None = None,
    ):
        self.prices_by_url = {url: list(prices) for url, prices in prices_by_url.items()}
        self.name = name
        self.shop = shop
        self.rating = rating
        self.buy_link = buy_link
        self.fetched_urls: list[str] = []

    async def fetch(self, url: str) -> TrackedProduct | None:
        self.fetched_urls.append(url)
        queue = self.prices_by_url.get(url, [])
        price = queue.pop(0) if queue else None
        if price is None:
            return None
        return TrackedProduct(name=self.name, price=price, shop=self.shop, rating=self.rating, buy_link=self.buy_link)


class RecordingPhotoStorage:
    def __init__(self, local_path: str | None = "photos/stored.jpg"):
        self.local_path = local_path
        self.saved_file_ids: list[str] = []

    async def save(self, telegram_file_id: str, telegram_file_unique_id: str) -> str | None:
        self.saved_file_ids.append(telegram_file_id)
        return self.local_path


class FixedRealtimeFeed:
    def __init__(self, snapshot: RealtimeSnapshot | None):
        self.snapshot = snapshot
        self.fetch_calls = 0

    async def fetch(self) -> RealtimeSnapshot | None:
        self.fetch_calls += 1
        return self.snapshot


class FixedRouteShapeCatalog:
    def __init__(self, shapes: dict[str, RouteShape] | None = None):
        self.shapes = shapes or {}
        self.refresh_calls = 0

    async def shape_for_route(self, route_id: str) -> RouteShape | None:
        return self.shapes.get(route_id)

    async def refresh(self) -> None:
        self.refresh_calls += 1


class FixedAirRaidAlertSource:
    def __init__(self, active: bool | None):
        self.active = active

    async def is_alert_active(self) -> bool | None:
        return self.active


class FixedLanguageModel:
    def __init__(self, answer: str | None, later_answers: Sequence[str] = ()):
        self.answers = [answer, *later_answers]
        self.conversations: list[list[ConversationTurn]] = []
        self.system_instructions: list[str] = []

    async def generate(self, conversation: Sequence[ConversationTurn], system_instruction: str) -> str | None:
        self.conversations.append(list(conversation))
        self.system_instructions.append(system_instruction)
        return self.answers[min(len(self.conversations) - 1, len(self.answers) - 1)]


class ExhaustedLanguageModel:
    def __init__(self, is_daily: bool = True):
        self.is_daily = is_daily

    async def generate(self, conversation: Sequence[ConversationTurn], system_instruction: str) -> str | None:
        raise QuotaExhausted(is_daily=self.is_daily)


class FixedKnowledgeSource:
    def __init__(self, facts: str):
        self.facts = facts

    async def gather(self) -> str:
        return self.facts
