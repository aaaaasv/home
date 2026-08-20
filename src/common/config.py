from datetime import time
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ALLOWED_USER_IDS: str = ""
    TELEGRAM_REMINDER_CHAT_ID: int = 0
    TELEGRAM_PLANTS_TOPIC_ID: int = 0
    PLANTS_TOPIC_TITLE: str = "plants"
    TELEGRAM_SHOPPING_TOPIC_ID: int = 0
    SHOPPING_TOPIC_TITLE: str = "shopping"
    TELEGRAM_PLACES_TOPIC_ID: int = 0
    PLACES_TOPIC_TITLE: str = "places"
    TELEGRAM_CHORES_TOPIC_ID: int = 0
    CHORES_TOPIC_TITLE: str = "chores"

    DATABASE_PATH: str = "home.db"
    PHOTO_STORAGE_PATH: str = "photos"

    # what the bot calls itself where it signs something — an annotation on a plant sheet, say.
    # a name, not a brand: set it to whatever the household actually calls the thing
    BOT_DISPLAY_NAME: str = "bot"

    TIMEZONE: str = "Europe/Kyiv"
    DAILY_DIGEST_TIME: str = "09:00"
    # weekends get a later one — the digest is the same, the hour is not. empty means "same as weekdays"
    WEEKEND_DIGEST_TIME: str = ""
    # the digest is not sent before this time, and checked this often so a pi that was down still catches up
    DIGEST_CHECK_INTERVAL_MINUTES: int = 30
    RECENT_CARE_GUARD_HOURS: int = 12

    # a chore's deadline card appears this many days before it is due; the card is checked hourly, but only within
    # this waking-hours window, so a crossing pings at a civilized time rather than at 03:00
    CHORE_REMINDER_LEAD_DAYS: int = 1
    CHORE_REMINDER_START_HOUR: int = 9
    CHORE_REMINDER_END_HOUR: int = 21

    CLIMATE_SENSOR_ENABLED: bool = False
    CLIMATE_SENSOR_I2C_BUS: int = 1
    CLIMATE_SENSOR_I2C_ADDRESS: int = 0x44
    CLIMATE_SAMPLE_INTERVAL_SECONDS: int = 60
    # a plant alerts only when the median over this window crosses its ideal range — a heated flat is dry all winter,
    # so a level check would fire every day and get the group muted
    CLIMATE_ALERT_WINDOW_HOURS: int = 24
    # the median must climb this far back inside the range before "fixed" is announced, so it cannot flap on the edge
    CLIMATE_HYSTERESIS_TEMPERATURE_CELSIUS: float = 1.0
    CLIMATE_HYSTERESIS_HUMIDITY_PERCENT: float = 3.0

    # the daily weather digest lives in its own topic so its always-on chatter can be muted without silencing plants
    WEATHER_DIGEST_ENABLED: bool = False
    TELEGRAM_WEATHER_TOPIC_ID: int = 0
    WEATHER_TOPIC_TITLE: str = "climate"
    WEATHER_DIGEST_TIME: str = "08:00"
    # the morning digest then keeps itself current in place: a silent edit every N minutes, only during the hours
    # someone might look (inclusive hour range), so a glance at the topic shows now, not the 08:00 snapshot
    WEATHER_REFRESH_MINUTES: int = 15
    WEATHER_REFRESH_START_HOUR: int = 8
    WEATHER_REFRESH_END_HOUR: int = 22
    # where the forecast is for — required once the digest is on. no default: a coordinate
    # is a place, and a place belongs in configuration, not in the source
    WEATHER_LATITUDE: float = 0.0
    WEATHER_LONGITUDE: float = 0.0

    # the gree-protocol air conditioner on the local network; give it a fixed dhcp lease so the address holds
    AIR_CONDITIONER_ENABLED: bool = False
    AIR_CONDITIONER_HOST: str = ""
    AIR_CONDITIONER_MAC: str = ""
    AIR_CONDITIONER_ROOM: str = ""
    AIR_CONDITIONER_MIN_TEMPERATURE: int = 16
    AIR_CONDITIONER_MAX_TEMPERATURE: int = 30
    # say something only once a run, and only after long enough that it reads as a forgotten unit
    AIR_CONDITIONER_LONG_RUN_HOURS: int = 6
    AIR_CONDITIONER_CHECK_MINUTES: int = 20

    # the raspberry pi's own vitals, watched from inside the container via sysfs — silent unless something is wrong
    SYSTEM_HEALTH_ENABLED: bool = False
    TELEGRAM_TECH_TOPIC_ID: int = 0
    TECH_TOPIC_TITLE: str = "service"
    PI_TEMPERATURE_ALERT_CELSIUS: float = 75.0
    # a couple of degrees of hysteresis so a temperature idling near the limit cannot flap the alert
    PI_TEMPERATURE_RECOVERY_CELSIUS: float = 68.0
    PI_DISK_ALERT_PERCENT: float = 90.0
    PI_DISK_RECOVERY_PERCENT: float = 85.0
    PI_HEALTH_CHECK_MINUTES: int = 10

    # presence: the router's local api tells the bot which phones are on Wi-Fi, to catch "everyone left, ac still on"
    PRESENCE_ENABLED: bool = False
    ROUTER_HOST: str = "192.168.50.1"
    ROUTER_USERNAME: str = ""
    ROUTER_PASSWORD: str = ""
    PRESENCE_PHONE_MACS: str = ""
    PRESENCE_CHECK_MINUTES: int = 3
    # a phone deep-sleeps off Wi-Fi for minutes, so it counts as gone only after this long unseen
    PRESENCE_AWAY_GRACE_MINUTES: int = 15

    # once a day the bot re-reads every /track-ed hotline item and speaks only on a new low; dormant until used
    # the tracked price is the cheapest offer from a shop that either clears the rating bar or is trusted by hand,
    # so a no-name shop undercutting everyone cannot become the alert
    PRICE_WATCH_TIME: str = "07:30"
    HOTLINE_MINIMUM_RATING: int = 80
    HOTLINE_MINIMUM_REVIEWS: int = 100
    # big national chains you can physically walk into, whose hotline service rating sits under the bar anyway:
    # allo, stylus, vodafone, citrus, moyo, elmir, itbox. edit in .env to drop or add hotline firm ids
    HOTLINE_TRUSTED_FIRM_IDS: str = "862,287,32066,2248,11054,1531,3300"
    # prices come from hotline's graphql api, which needs a token minted by any live product page; we lift one from
    # the first product under this evergreen category. cityId 187 is kyiv — the price list is city-scoped
    HOTLINE_DONOR_CATEGORY_URL: str = "https://hotline.ua/ua/computer/noutbuki/"
    HOTLINE_CITY_ID: int = 187

    # ⚡ світло: the EcoFlow Delta 2 over local ble lives in its own topic, so a blackout alert can push while the
    # always-on schedule chatter stays a silent, self-editing card — the shopping-list rule applied to power
    TELEGRAM_POWER_TOPIC_ID: int = 0
    POWER_TOPIC_TITLE: str = "power"
    ECOFLOW_ENABLED: bool = False
    # obtained once from an online account login, then the station is read fully offline over ble; not the password
    ECOFLOW_USER_ID: str = ""
    ECOFLOW_BLE_MAC: str = ""
    ECOFLOW_BLE_SCAN_SECONDS: int = 12
    # the poll that samples the held-open link for the conservation tracker (the /eco card reads it live, not here)
    ECOFLOW_POLL_MINUTES: int = 10
    # the link must stay down at least this long before the station counts as shelved, so a brief ble drop or a
    # restart caught mid-reconnect cannot falsely trip conservation (the manual /conserve toggle is instant)
    ECOFLOW_CONSERVED_AFTER_MINUTES: int = 20
    # the conservation card is re-evaluated this often while the station is shelved — day-based advisories change
    # slowly, but a few-hourly cadence surfaces "just shelved" guidance without waiting for the next morning
    ECOFLOW_CONSERVATION_CHECK_HOURS: int = 4
    # yasno outage schedule — the daily digest is silent when nothing is planned. the group, region and
    # distribution operator identify one address's supply, so they are configuration, never defaults
    YASNO_ENABLED: bool = False
    YASNO_GROUP: str = ""
    YASNO_REGION_ID: int = 0
    YASNO_DSO_ID: int = 0
    # re-read this often: emergency outages get added mid-day; keep it under the pre-outage lead so no ping is missed
    YASNO_POLL_MINUTES: int = 20
    YASNO_DIGEST_TIME: str = "07:00"
    # a planned outage gets one heads-up this many minutes before it starts — a bare fact, no advice
    YASNO_PRE_OUTAGE_LEAD_MINUTES: int = 30

    # transit: on-demand arrival card for the family stop — the endpoints are raw-ip gov hosts that may move
    TRANSIT_ENABLED: bool = False
    TELEGRAM_TRANSIT_TOPIC_ID: int = 0
    TRANSIT_TOPIC_TITLE: str = "transit"
    TRANSIT_REALTIME_URL: str = "http://193.23.225.214:732/api/realtime"
    TRANSIT_STATIC_URL: str = "http://193.23.225.211:8002/export-gtfs-static"
    # cached beside the db under ./data (the photos pattern); the static host is slow, so it refreshes only weekly
    TRANSIT_STATIC_CACHE_PATH: str = "gtfs-static"
    TRANSIT_STATIC_REFRESH_DAYS: int = 7
    # the stop to watch. no defaults: a stop id and its coordinates name the street somebody lives on
    TRANSIT_STOP_ID: str = ""
    TRANSIT_STOP_LATITUDE: float = 0.0
    TRANSIT_STOP_LONGITUDE: float = 0.0
    # a point every watched route heads toward. it picks each route's correct direction — the shape ending
    # nearest here — because the sparse stop_times cannot give direction on their own
    TRANSIT_DESTINATION_LATITUDE: float = 0.0
    TRANSIT_DESTINATION_LONGITUDE: float = 0.0
    # "route_id:short_name:kind", comma separated; kind is trolleybus, bus or tram
    TRANSIT_ROUTES: str = ""
    # the card re-estimates this often, for this long, then freezes — long enough to put shoes on, never a push
    TRANSIT_CARD_REFRESH_SECONDS: int = 30
    TRANSIT_CARD_WINDOW_MINUTES: int = 5

    # every new plant photo is compared with the previous one by claude; off until an api key is in place
    PLANT_PHOTO_REVIEW_ENABLED: bool = False
    ANTHROPIC_API_KEY: str = ""
    PLANT_PHOTO_REVIEW_MODEL: str = "claude-opus-4-8"

    # the assistant: a grounded home helper in its own topic, answering only from the curated knowledge file via a
    # swappable LanguageModel (default: Google's free-tier Gemini). off until a free api key is set
    # the free Gemini tier trains on inputs and humans may read them — keep NO secrets in the knowledge file
    ASSISTANT_ENABLED: bool = False
    TELEGRAM_ASSISTANT_TOPIC_ID: int = 0
    ASSISTANT_TOPIC_TITLE: str = "ask"
    # the curated facts file that ships with the code (edit it + redeploy); keep NO secrets in it
    ASSISTANT_KNOWLEDGE_PATH: str = "home-knowledge.md"
    GEMINI_API_KEY: str = ""
    # pinned on purpose: the "…-latest" alias has no free-tier quota for google-search grounding (429), while this
    # stable model does — and it is multimodal, so it serves the assistant's search+vision and the photo review
    GEMINI_MODEL: str = "gemini-2.5-flash"

    LOG_LEVEL: str = "INFO"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.DATABASE_PATH}"

    @property
    def migration_database_url(self) -> str:
        return f"sqlite:///{self.DATABASE_PATH}"

    @property
    def allowed_telegram_user_ids(self) -> frozenset[int]:
        return frozenset(
            int(user_id.strip()) for user_id in self.TELEGRAM_ALLOWED_USER_IDS.split(",") if user_id.strip()
        )

    @property
    def plants_topic_id(self) -> int | None:
        # telegram wants the parameter absent, not zero, when the digest goes to a chat without topics
        return self.TELEGRAM_PLANTS_TOPIC_ID or None

    @property
    def shopping_topic_id(self) -> int | None:
        return self.TELEGRAM_SHOPPING_TOPIC_ID or None

    @property
    def places_topic_id(self) -> int | None:
        return self.TELEGRAM_PLACES_TOPIC_ID or None

    @property
    def chores_topic_id(self) -> int | None:
        return self.TELEGRAM_CHORES_TOPIC_ID or None

    @property
    def weather_topic_id(self) -> int | None:
        return self.TELEGRAM_WEATHER_TOPIC_ID or None

    @property
    def tech_topic_id(self) -> int | None:
        return self.TELEGRAM_TECH_TOPIC_ID or None

    @property
    def power_topic_id(self) -> int | None:
        return self.TELEGRAM_POWER_TOPIC_ID or None

    @property
    def transit_topic_id(self) -> int | None:
        return self.TELEGRAM_TRANSIT_TOPIC_ID or None

    @property
    def assistant_topic_id(self) -> int | None:
        return self.TELEGRAM_ASSISTANT_TOPIC_ID or None

    @property
    def presence_phone_macs(self) -> set[str]:
        return {mac.strip().upper() for mac in self.PRESENCE_PHONE_MACS.split(",") if mac.strip()}

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)

    @property
    def daily_digest_time(self) -> time:
        return time.fromisoformat(self.DAILY_DIGEST_TIME)

    @property
    def weekend_digest_time(self) -> time:
        return time.fromisoformat(self.WEEKEND_DIGEST_TIME) if self.WEEKEND_DIGEST_TIME else self.daily_digest_time

    @property
    def weather_digest_time(self) -> time:
        return time.fromisoformat(self.WEATHER_DIGEST_TIME)

    @property
    def price_watch_time(self) -> time:
        return time.fromisoformat(self.PRICE_WATCH_TIME)

    @property
    def yasno_digest_time(self) -> time:
        return time.fromisoformat(self.YASNO_DIGEST_TIME)

    @property
    def hotline_trusted_firm_ids(self) -> frozenset[int]:
        return frozenset(
            int(firm_id.strip()) for firm_id in self.HOTLINE_TRUSTED_FIRM_IDS.split(",") if firm_id.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
