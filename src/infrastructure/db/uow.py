from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.main import get_session_maker
from src.infrastructure.repositories.air_conditioner_run import AirConditionerRunRepository
from src.infrastructure.repositories.care_digest_delivery import CareDigestDeliveryRepository
from src.infrastructure.repositories.care_event import CareEventRepository
from src.infrastructure.repositories.care_schedule import CareScheduleRepository
from src.infrastructure.repositories.chore import ChoreRepository
from src.infrastructure.repositories.conservation import ConservationRepository
from src.infrastructure.repositories.family_member import FamilyMemberRepository
from src.infrastructure.repositories.forum_topic import ForumTopicRepository
from src.infrastructure.repositories.place import PlaceRepository
from src.infrastructure.repositories.plant import PlantRepository
from src.infrastructure.repositories.plant_climate_alert import PlantClimateAlertRepository
from src.infrastructure.repositories.plant_photo import PlantPhotoRepository
from src.infrastructure.repositories.posted_message import PostedMessageRepository
from src.infrastructure.repositories.price_check import PriceCheckRepository
from src.infrastructure.repositories.room_climate import (
    RoomClimateAlertRepository,
    RoomClimateDayRepository,
    RoomClimateReadingRepository,
)
from src.infrastructure.repositories.shopping_item import ShoppingItemRepository


class UnitOfWork:
    def __init__(self, session_factory: Callable[[], AsyncSession] | None = None):
        self.session_factory = session_factory or get_session_maker()
        self.session: AsyncSession | None = None
        self.plants: PlantRepository | None = None
        self.care_schedules: CareScheduleRepository | None = None
        self.care_events: CareEventRepository | None = None
        self.plant_photos: PlantPhotoRepository | None = None
        self.forum_topics: ForumTopicRepository | None = None
        self.shopping_items: ShoppingItemRepository | None = None
        self.price_checks: PriceCheckRepository | None = None
        self.places: PlaceRepository | None = None
        self.chores: ChoreRepository | None = None
        self.family_members: FamilyMemberRepository | None = None
        self.room_climate_readings: RoomClimateReadingRepository | None = None
        self.room_climate_alerts: RoomClimateAlertRepository | None = None
        self.room_climate_days: RoomClimateDayRepository | None = None
        self.plant_climate_alerts: PlantClimateAlertRepository | None = None
        self.air_conditioner_runs: AirConditionerRunRepository | None = None
        self.care_digest_deliveries: CareDigestDeliveryRepository | None = None
        self.posted_messages: PostedMessageRepository | None = None
        self.conservation: ConservationRepository | None = None

    async def __aenter__(self):
        self.session = self.session_factory()
        self.plants = PlantRepository(session=self.session)
        self.care_schedules = CareScheduleRepository(session=self.session)
        self.care_events = CareEventRepository(session=self.session)
        self.plant_photos = PlantPhotoRepository(session=self.session)
        self.forum_topics = ForumTopicRepository(session=self.session)
        self.shopping_items = ShoppingItemRepository(session=self.session)
        self.price_checks = PriceCheckRepository(session=self.session)
        self.places = PlaceRepository(session=self.session)
        self.chores = ChoreRepository(session=self.session)
        self.family_members = FamilyMemberRepository(session=self.session)
        self.room_climate_readings = RoomClimateReadingRepository(session=self.session)
        self.room_climate_alerts = RoomClimateAlertRepository(session=self.session)
        self.room_climate_days = RoomClimateDayRepository(session=self.session)
        self.plant_climate_alerts = PlantClimateAlertRepository(session=self.session)
        self.air_conditioner_runs = AirConditionerRunRepository(session=self.session)
        self.care_digest_deliveries = CareDigestDeliveryRepository(session=self.session)
        self.posted_messages = PostedMessageRepository(session=self.session)
        self.conservation = ConservationRepository(session=self.session)
        return self

    async def __aexit__(self, exception_type, exception_value, exception_traceback):
        try:
            if exception_type:
                await self.rollback()
            else:
                await self.commit()
        finally:
            await self.session.close()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()
