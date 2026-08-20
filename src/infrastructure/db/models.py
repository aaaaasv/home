from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from src.common.time import current_time
from src.infrastructure.db.base import Base
from src.infrastructure.db.types import UtcDateTime


class Plant(Base):
    __tablename__ = "plants"
    __table_args__ = (
        Index("uq_plants_active_name", "name", unique=True, sqlite_where=text("is_archived = 0")),
        Index("ix_plants_is_archived_name", "is_archived", "name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    species = Column(String(128), nullable=True)
    location = Column(String(128), nullable=True)
    notes = Column(Text, nullable=True)
    ideal_temperature_min_celsius = Column(Float, nullable=True)
    ideal_temperature_max_celsius = Column(Float, nullable=True)
    ideal_humidity_min_percent = Column(Float, nullable=True)
    ideal_humidity_max_percent = Column(Float, nullable=True)
    # the word a tag carries instead of a number
    slug = Column(String(80), nullable=True, index=True, unique=True)
    # what a herbarium sheet records beyond the care schedule
    provenance = Column(Text, nullable=True)
    native_range = Column(String(160), nullable=True)
    substrate = Column(String(160), nullable=True)
    toxicity = Column(String(160), nullable=True)
    added_by_telegram_user_id = Column(BigInteger, nullable=False)
    is_archived = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(UtcDateTime, default=current_time, nullable=False)
    updated_at = Column(UtcDateTime, default=current_time, onupdate=current_time, nullable=False)


class CareSchedule(Base):
    __tablename__ = "care_schedules"
    __table_args__ = (
        UniqueConstraint("plant_id", "task_type", name="uq_care_schedules_plant_task_type"),
        Index("ix_care_schedules_next_due_on", "next_due_on"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True)
    task_type = Column(String(20), nullable=False)
    interval_days = Column(Integer, nullable=False)
    next_due_on = Column(Date, nullable=False)
    last_performed_at = Column(UtcDateTime, nullable=True)
    instructions = Column(Text, nullable=True)
    # the growing-season window a task lives in; null on both means year-round (watering), a range gates fertilizing
    season_start_month = Column(Integer, nullable=True)
    season_end_month = Column(Integer, nullable=True)
    created_at = Column(UtcDateTime, default=current_time, nullable=False)
    updated_at = Column(UtcDateTime, default=current_time, onupdate=current_time, nullable=False)


class CareEvent(Base):
    __tablename__ = "care_events"
    __table_args__ = (Index("ix_care_events_plant_id_task_type_performed_at", "plant_id", "task_type", "performed_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False)
    task_type = Column(String(20), nullable=False)
    performed_at = Column(UtcDateTime, nullable=False)
    performed_by_telegram_user_id = Column(BigInteger, nullable=False)
    performed_by_display_name = Column(String(128), nullable=False)
    note = Column(Text, nullable=True)
    # the due date this record pushed aside, so undoing it puts the schedule back exactly where it stood
    previous_next_due_on = Column(Date, nullable=True)
    created_at = Column(UtcDateTime, default=current_time, nullable=False)


class PlantPhoto(Base):
    __tablename__ = "plant_photos"
    __table_args__ = (Index("ix_plant_photos_plant_id_taken_at", "plant_id", "taken_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False)
    telegram_file_id = Column(String(255), nullable=False)
    telegram_file_unique_id = Column(String(64), nullable=False)
    local_path = Column(String(512), nullable=True)
    caption = Column(Text, nullable=True)
    added_by_telegram_user_id = Column(BigInteger, nullable=False)
    taken_at = Column(UtcDateTime, nullable=False)
    created_at = Column(UtcDateTime, default=current_time, nullable=False)


class CareDigestDelivery(Base):
    """The day the care digest was last sent — a periodic job sends it once even if the pi was down at digest time"""

    __tablename__ = "care_digest_deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sent_on = Column(Date, nullable=False)
    created_at = Column(UtcDateTime, default=current_time, nullable=False)


class RoomClimateReading(Base):
    __tablename__ = "room_climate_readings"
    __table_args__ = (Index("ix_room_climate_readings_measured_at", "measured_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    temperature_celsius = Column(Float, nullable=False)
    relative_humidity_percent = Column(Float, nullable=False)
    measured_at = Column(UtcDateTime, nullable=False)


class RoomClimateAlert(Base):
    """Append-only: the newest row is the current state, so a restart cannot make the bot alert twice"""

    __tablename__ = "room_climate_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    is_air_dry = Column(Boolean, nullable=False)
    relative_humidity_percent = Column(Float, nullable=False)
    changed_at = Column(UtcDateTime, nullable=False)


class PlantClimateAlert(Base):
    """
    Append-only, one lane per (plant, dimension): the newest row is the current state and the last time it was
    announced. a restart cannot double-alert, and the weekly re-nag paces itself off notified_at.
    """

    __tablename__ = "plant_climate_alerts"
    __table_args__ = (Index("ix_plant_climate_alerts_plant_dimension_id", "plant_id", "dimension", "id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False)
    dimension = Column(String(16), nullable=False)
    status = Column(String(8), nullable=False)
    value = Column(Float, nullable=False)
    notified_at = Column(UtcDateTime, nullable=False)


class ShoppingItem(Base):
    __tablename__ = "shopping_items"
    __table_args__ = (Index("ix_shopping_items_bought_at_horizon", "bought_at", "horizon"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    horizon = Column(String(8), nullable=False)
    added_by_telegram_user_id = Column(BigInteger, nullable=False)
    added_by_display_name = Column(String(128), nullable=False)
    bought_at = Column(UtcDateTime, nullable=True)
    bought_by_display_name = Column(String(128), nullable=True)
    # a hotline product url turns the item into a tracked one; plain items leave it null
    hotline_url = Column(String(512), nullable=True)
    # a telegram file_id for a photo of the thing to buy — shown on the item's menu; null for text-only items
    photo_telegram_file_id = Column(String(256), nullable=True)
    # measurements, a link, anything the short name cannot carry; edited from the item's card
    note = Column(Text, nullable=True)
    created_at = Column(UtcDateTime, default=current_time, nullable=False)


class PriceCheck(Base):
    """One price reading for a tracked shopping item — the history gives both the low and the trend arrow"""

    __tablename__ = "price_checks"
    __table_args__ = (Index("ix_price_checks_item_id_checked_at", "shopping_item_id", "checked_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    shopping_item_id = Column(Integer, ForeignKey("shopping_items.id", ondelete="CASCADE"), nullable=False)
    price = Column(Integer, nullable=False)
    checked_at = Column(UtcDateTime, nullable=False)


class Place(Base):
    """Somewhere the family wants to go; once visited it stays as history rather than being deleted"""

    __tablename__ = "places"
    __table_args__ = (Index("ix_places_visited_at", "visited_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    link = Column(String(512), nullable=True)
    address = Column(String(256), nullable=True)
    note = Column(Text, nullable=True)
    # indoor/outdoor — unset for now, the weather-aware suggester will read it later
    setting = Column(String(8), nullable=True)
    added_by_telegram_user_id = Column(BigInteger, nullable=False)
    added_by_display_name = Column(String(128), nullable=False)
    visited_at = Column(UtcDateTime, nullable=True)
    visited_by_display_name = Column(String(128), nullable=True)
    created_at = Column(UtcDateTime, default=current_time, nullable=False)


class ForumTopic(Base):
    """The telegram forum topic a module posts into — the bot api cannot list topics, so it remembers its own"""

    __tablename__ = "forum_topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_name = Column(String(32), nullable=False, unique=True)
    chat_id = Column(BigInteger, nullable=False)
    message_thread_id = Column(Integer, nullable=False)
    created_at = Column(UtcDateTime, default=current_time, nullable=False)
    updated_at = Column(UtcDateTime, default=current_time, onupdate=current_time, nullable=False)


class AirConditionerRun(Base):
    """
    One row per continuous run, opened when the unit is first seen on and closed when it is first seen off.
    it lives in the database rather than in memory so a deploy in the middle of a hot afternoon does not reset
    the clock and swallow the reminder.
    """

    __tablename__ = "air_conditioner_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(UtcDateTime, nullable=False)
    ended_at = Column(UtcDateTime, nullable=True)
    notified_at = Column(UtcDateTime, nullable=True)


class Chore(Base):
    """Something to do; an optional deadline turns it from a silent someday item into a reminded one"""

    __tablename__ = "chores"
    __table_args__ = (Index("ix_chores_completed_at_due_on", "completed_at", "due_on"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    # null = someday: a silent list item that never nags; a date makes it a reminded chore
    due_on = Column(Date, nullable=True)
    added_by_telegram_user_id = Column(BigInteger, nullable=False)
    added_by_display_name = Column(String(128), nullable=False)
    # a person this chore is about: its deadline card @mentions them so the reminder reaches them, not just the group
    assignee_telegram_user_id = Column(BigInteger, nullable=True)
    assignee_display_name = Column(String(128), nullable=True)
    completed_at = Column(UtcDateTime, nullable=True)
    completed_by_display_name = Column(String(128), nullable=True)
    created_at = Column(UtcDateTime, default=current_time, nullable=False)


class FamilyMember(Base):
    """The household roster, filled in by itself: every allowed member who writes is remembered by id and name,
    so a chore can be tagged to «Марта» by name and its reminder can @mention her — no configuration needed"""

    __tablename__ = "family_members"

    telegram_user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    # what telegram calls them — refreshed on every message, so it cannot hold a chosen name
    display_name = Column(String(128), nullable=False)
    # what they chose to be called; wins wherever a person is named
    preferred_name = Column(String(128), nullable=True)
    updated_at = Column(UtcDateTime, default=current_time, onupdate=current_time, nullable=False)


class PostedMessage(Base):
    """A message the bot posted and may later delete when it goes stale — one lane per kind (a digest, the ac card)"""

    __tablename__ = "posted_messages"
    __table_args__ = (Index("ix_posted_messages_kind", "kind"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(32), nullable=False)
    # what the message is about within its kind ("watering:5"), so one card can be dropped without the batch
    reference = Column(String(32), nullable=True)
    chat_id = Column(BigInteger, nullable=False)
    message_id = Column(Integer, nullable=False)
    created_at = Column(UtcDateTime, default=current_time, nullable=False)


class ConservationRecord(Base):
    """
    The storage regime for the one EcoFlow station, held as a single row. it keeps the last charge we saw and the
    moment we lost sight of it (conservation start), the mode, the last maintenance cycle, whether the charge has
    dipped to the floor since (so a full 60→0→100→60 cycle is recognised across polls and restarts), and the last
    advisory level shown (so a rise into yellow/red pings, while a steady state only edits the card in place).
    """

    __tablename__ = "conservation_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stored_percent = Column(Float, nullable=False)
    stored_at = Column(UtcDateTime, nullable=False)
    mode = Column(String(8), nullable=False, default="off", server_default="off")
    last_cycle_at = Column(UtcDateTime, nullable=True)
    is_conserved = Column(Boolean, nullable=False, default=False, server_default="0")
    # set when a person marks the state by hand; the poll then stops auto-flipping is_conserved until the station's
    # real reachability confirms the manual mark, so a flaky read cannot undo "put it into storage"
    manual_override = Column(Boolean, nullable=False, default=False, server_default="0")
    saw_low_since_cycle = Column(Boolean, nullable=False, default=False, server_default="0")
    last_advised_level = Column(String(8), nullable=True)
    updated_at = Column(UtcDateTime, default=current_time, onupdate=current_time, nullable=False)
