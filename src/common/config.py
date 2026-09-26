import json
from datetime import time
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.common.domain import Actor


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

    # the LAN web surface: one specimen sheet per plant, for whoever taps the NFC tag on the pot.
    # plain http by ip on purpose — dns is an extra dependency in this path, and an internal-CA
    # certificate warns every guest phone. the token is a capability scoped to *actions*: reading is open
    # on the lan, watering needs the key that is written into the tag
    WEB_ENABLED: bool = False
    WEB_PORT: int = 8080
    # a latch on the action button, not a lock — it stops an accidental tap, nothing more
    WEB_ACTOR_NAME: str = ""

    # the mqtt broker on the pi: how the house talks to anything that is not telegram. homebridge reads it
    # to put the air conditioner on a phone, zigbee2mqtt will write devices into it, and the bot stays the
    # only place decisions are made — what arrives here is a tap, never an automation
    MQTT_ENABLED: bool = False
    MQTT_HOST: str = "mosquitto"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    # every topic this bot owns hangs under it, so one subscription shows the whole surface
    MQTT_TOPIC_PREFIX: str = "home-bot"
    # a tile that lags a minute behind reality reads as broken, and the unit is polled locally anyway
    MQTT_PUBLISH_INTERVAL_SECONDS: int = 30

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
    # deliberately not 08:00. open-meteo sheds load exactly on the hour, and the digest's own fetch is the one
    # that decides whether the day has weather at all — firing it on the boundary lost the forecast repeatedly
    WEATHER_DIGEST_TIME: str = "08:03"
    # the morning digest then keeps itself current in place: a silent edit every N minutes, only during the hours
    # someone might look (inclusive hour range), so a glance at the topic shows now, not the 08:00 snapshot
    WEATHER_REFRESH_MINUTES: int = 15
    # an hour before the digest, so the last successful reading is minutes old rather than from last night. that
    # is what lets the digest survive its own fetch failing: the fallback only reaches back WEATHER_RECENT_MAX_AGE,
    # and starting at 8 left a nine-hour hole exactly where the fallback was needed
    WEATHER_REFRESH_START_HOUR: int = 7
    WEATHER_REFRESH_END_HOUR: int = 22
    # where the forecast is for — required once the digest is on. no default: a coordinate
    # is a place, and a place belongs in configuration, not in the source
    # pm2.5 from the volunteer sensors a few streets away, which replaces the modelled index in the digest
    # whenever they answer. the model is ~11 km wide and averages away exactly the local spikes that matter
    LOCAL_AIR_QUALITY_ENABLED: bool = False
    # the forecast coordinate is deliberately coarse — a few km either way changes nothing about the
    # weather. finding the sensors on your own street is the opposite problem, so it gets its own pair
    # and falls back to the weather one when unset
    LOCAL_AIR_QUALITY_LATITUDE: float = 0.0
    LOCAL_AIR_QUALITY_LONGITUDE: float = 0.0
    LOCAL_AIR_QUALITY_RADIUS_KM: float = 2.0
    LOCAL_AIR_QUALITY_TIMEOUT_SECONDS: float = 10.0
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
    # the media server's disks, read over the same http agent that serves its battery. smartd on that machine
    # already watches them every half hour and then mails local root, which nobody reads — this is the path
    # that actually reaches a person. the probe there refreshes hourly, so asking faster only re-reads a file
    MEDIA_SERVER_DISKS_URL: str = ""
    MEDIA_SERVER_DISKS_TIMEOUT_SECONDS: float = 5.0
    MEDIA_SERVER_DISK_CHECK_HOURS: int = 1

    # presence: the router's local api tells the bot which phones are on Wi-Fi, to catch "everyone left, ac still on"
    PRESENCE_ENABLED: bool = False
    ROUTER_HOST: str = ""
    ROUTER_USERNAME: str = ""
    ROUTER_PASSWORD: str = ""
    PRESENCE_PHONE_MACS: str = ""
    PRESENCE_CHECK_MINUTES: int = 3
    # a phone deep-sleeps off Wi-Fi for minutes, so it counts as gone only after this long unseen
    PRESENCE_AWAY_GRACE_MINUTES: int = 15
    # ── зустріч на порозі ─────────────────────────────────────────────────────
    ARRIVAL_LIGHT_ENABLED: bool = False
    PRESENCE_LATITUDE: float = 0.0
    PRESENCE_LONGITUDE: float = 0.0
    ARRIVAL_LIGHT_PERCENT: float = 20.0
    # скільки телефона має не бути, щоб поява рахувалась поверненням. у лозі роутера видно, як пристрій
    # відпадає і вертається за три секунди — тому поріг у десятках хвилин, а не в секундах
    ARRIVAL_AWAY_MINUTES: int = 30
    ARRIVAL_LIGHT_MINUTES: int = 10

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
    # the grid is watched far more often than the storage regime: this is the one message worth being early
    ECOFLOW_MAINS_CHECK_MINUTES: int = 1
    # a change must hold for this many readings before it is announced — one reading is a blip, and this
    # message wakes the family
    ECOFLOW_MAINS_CONFIRMATIONS: int = 2
    # the runtime estimate swings with the fridge cycling, so asking every minute would only add noise
    ECOFLOW_FORECAST_CHECK_MINUTES: int = 5
    ECOFLOW_CONSERVED_AFTER_MINUTES: int = 20
    # the conservation card is re-evaluated this often while the station is shelved — day-based advisories change
    # slowly, but a few-hourly cadence surfaces "just shelved" guidance without waiting for the next morning
    ECOFLOW_CONSERVATION_CHECK_HOURS: int = 4
    # the pi's own x728 hat — the only direct reading of the wall socket in the flat, so mains detection prefers
    # it over the station's inference and keeps answering while the station is shelved or not owned. the board is
    # watched by a host agent (home-infrastructure/pi/x728), which also halts the pi on a dying pack; the bot only
    # reads what that agent publishes, so it needs no device mounts of its own
    PI_UPS_ENABLED: bool = False
    PI_UPS_STATE_PATH: str = "/run/x728/state.json"
    # the agent republishes every few seconds — a reading older than this means it stopped, and a stale
    # "mains present" would announce the light coming back in the middle of an outage
    PI_UPS_STALE_AFTER_SECONDS: int = 120
    # the led strip on the server shelf, aimed at the switchboard: it comes on by itself when the grid drops and
    # goes off when the changeover is thrown, and that half runs on the host (home-infrastructure/pi/panel-light)
    # whether or not this container is up. the bot only offers the hand on it — a lamp tile in apple home
    # the soil probes: which zigbee sensor sits in which plant, as {"soil-peperoni": 2}. a jump in moisture
    # between two readings is somebody watering, and the bot records the care itself rather than waiting for
    # the button. the map is per-home, so it lives here and not in the code
    PLANT_SOIL_SENSORS: str = ""
    # how many percentage points of soil moisture make a jump. watering shows up as tens of points; drift and
    # sensor noise are a couple, so anything in between is deliberately ignored
    PLANT_SOIL_JUMP_POINTS: float = 10.0
    # and the level it has to reach, so a probe twitching around zero in bone-dry soil never counts as a pour
    PLANT_SOIL_WET_MINIMUM_PERCENT: float = 15.0
    ZIGBEE_TOPIC_PREFIX: str = "zigbee2mqtt"
    # which room's air each sensor speaks for, as {"temp-bedroom": "спальня"}. a sensor missing from the map is
    # not followed at all, which is how a probe pulled out of a pot stops writing rows the moment it is unmapped
    SENSOR_ROOMS: str = ""
    # how long full-resolution readings are kept. the sensors report on change, so a busy one writes tens of rows
    # an hour — a week is enough to re-read an experiment, and everything older lives in the daily summaries
    SENSOR_HISTORY_RAW_DAYS: int = 7
    SENSOR_FOLD_INTERVAL_MINUTES: int = 60
    PLANT_SOIL_ACTOR_NAME: str = "датчик"
    # ── повітряні загрози ─────────────────────────────────────────────────────
    AIR_THREATS_ENABLED: bool = False
    # куди писати: особистий чат власника, а не сімейна група — потік галасливий і цікавий одній людині
    AIR_THREATS_CHAT_ID: int = 0
    AIR_THREATS_LATITUDE: float = 0.0
    AIR_THREATS_LONGITUDE: float = 0.0
    # «просто тут»: настільки близько, що важливо будь-що й у будь-якому напрямку
    AIR_THREATS_OVERHEAD_KILOMETRES: float = 25.0
    # а далі — лише те, що націлене сюди, і лише коли лишилось стільки хвилин підльоту. хвилини, а не
    # кілометри: ті самі 70 км це 23 хвилини поршневого шахеда і 41 секунда чогось на М5
    AIR_THREATS_WARNING_MINUTES: float = 10.0
    AIR_THREATS_APPROACH_DEGREES: float = 30.0
    # мапа дає курс, але ніколи не дає швидкості — беремо типову за типом цілі, км/год
    AIR_THREATS_SPEEDS: str = '{"uav": 180, "fpv": 120, "missile": 800, "ballistic": 2400, "kab": 900, "aircraft": 700}'
    # незнайомий тип рахуємо найшвидшим із розумного: попередити зарано коштує погляду, запізно — усього сенсу
    AIR_THREATS_DEFAULT_SPEED: float = 2400.0
    # скільки ціль має не показуватись на мапі, перш ніж вважати, що вона зникла
    AIR_THREATS_STALE_SECONDS: int = 180
    # усе термінове приходить сокетом; ця джоба лише закриває картки, тому і ходить ліниво
    AIR_THREATS_SWEEP_SECONDS: int = 120
    # ── світло на тривогу ─────────────────────────────────────────────────────
    ALERT_LIGHT_ENABLED: bool = False
    # тільки червоний рівень: жовта дронова загроза триває годинами кілька ночей на тиждень, і світло,
    # яке відповідає на кожну з них, вимикають назавжди — а тоді його немає тієї ночі, коли воно потрібне
    ALERT_LIGHT_REGION: str = "м. Київ"
    ALERT_LIGHT_PERCENT: float = 20.0
    # сокет дає секунди, але мовчить, коли в країні нічого не змінюється — і тоді тиша не відрізняється
    # від обриву. ця перевірка ходить резервним опитуванням і задає найгіршу можливу затримку
    ALERT_LIGHT_CHECK_SECONDS: int = 30
    PANEL_LIGHT_ENABLED: bool = False
    PANEL_LIGHT_STATE_PATH: str = "/run/panel-light/state.json"
    PANEL_LIGHT_COMMAND_PATH: str = "/run/panel-light/command.json"
    # the reserve board: all four backup layers on one screen, one column, and that column is hours. it needs the
    # station, the hat and the router all configured, because a row it cannot read honestly is a row it must not
    # draw — so it registers only when every source it names is there
    RESERVE_ENABLED: bool = False
    # every tick while the flat is on battery, since that is the hour anyone opens it; on the grid the picture
    # does not move minute to minute, so the board is only rewritten every few
    RESERVE_CHECK_MINUTES: int = 1
    RESERVE_ON_GRID_REFRESH_MINUTES: int = 5
    # the router has no data interface at all, so its row is a tcp handshake to the admin port and nothing more.
    # a router that is up answers in milliseconds on the lan; anything slower than this is already an outage
    RESERVE_ROUTER_PORT: int = 80
    RESERVE_ROUTER_TIMEOUT_SECONDS: float = 3.0
    # the media server publishes its own battery over http, from the agent in home-infrastructure/server. an
    # endpoint rather than ssh or mqtt: the bot's container holds no keys to other machines, and opening the
    # broker to the lan would widen the blast radius of any compromised wi-fi device for the sake of four numbers
    RESERVE_MEDIA_SERVER_URL: str = ""
    RESERVE_MEDIA_SERVER_TIMEOUT_SECONDS: float = 3.0
    # the agent stamps every response, so a frozen box or a caching proxy cannot pass an old reading off as live
    RESERVE_MEDIA_SERVER_STALE_AFTER_SECONDS: int = 120
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

    # the weekly paper: a half-page crossword the lan printer prints on its own. the printing is the point as much
    # as the puzzle — an inkjet that fires no ink for a week starts to clog. the queue is the cups container that
    # carries epson's driver; gemini words are used when GEMINI_API_KEY is set, the bundled word bank otherwise
    NEWSPAPER_ENABLED: bool = False
    NEWSPAPER_PRINT_QUEUE_URI: str = ""
    NEWSPAPER_TITLE: str = ""
    # mon … sun; retries run every half hour for 32 hours after this, so a printer off at lunch still gets its page
    NEWSPAPER_PRINT_WEEKDAY: str = "sat"
    NEWSPAPER_PRINT_TIME: str = "13:00"

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
    # names an unfamiliar plant from the photo sent while adding it, so the species and the watering rhythm
    # are confirmed rather than typed. shares the gemini key and its free-tier quota with the review above
    PLANT_IDENTIFICATION_ENABLED: bool = False
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
    def plant_by_soil_sensor(self) -> dict[str, int]:
        """Which plant each probe stands in; an unreadable map is no map, not a crash on boot."""
        if not self.PLANT_SOIL_SENSORS.strip():
            return {}
        try:
            return {str(sensor): int(plant_id) for sensor, plant_id in json.loads(self.PLANT_SOIL_SENSORS).items()}
        except (ValueError, AttributeError):
            return {}

    @property
    def threat_speeds(self) -> dict[str, float]:
        """How fast each kind usually flies; an unreadable map is no map, not a crash on boot."""
        if not self.AIR_THREATS_SPEEDS.strip():
            return {}
        try:
            return {str(kind): float(speed) for kind, speed in json.loads(self.AIR_THREATS_SPEEDS).items()}
        except (ValueError, AttributeError):
            return {}

    @property
    def room_by_sensor(self) -> dict[str, str]:
        """Which room each sensor stands in; an unreadable map is no map, not a crash on boot."""
        if not self.SENSOR_ROOMS.strip():
            return {}
        try:
            return {str(sensor): str(room) for sensor, room in json.loads(self.SENSOR_ROOMS).items()}
        except (ValueError, AttributeError):
            return {}

    @property
    def recorded_sensors(self) -> dict[str, str | None]:
        """Every sensor worth writing down, and its room — a probe stands in a pot and has none."""
        sensors: dict[str, str | None] = {sensor: None for sensor in self.plant_by_soil_sensor}
        sensors.update(self.room_by_sensor)
        return sensors

    @property
    def sensor_actor(self) -> Actor:
        """Who the probe records care as — nobody pressed anything, and the history must not pretend otherwise."""
        return Actor(telegram_user_id=0, display_name=self.PLANT_SOIL_ACTOR_NAME)

    @property
    def web_actor(self) -> Actor:
        """Who the sheet records care as — a tap on a pot has no Telegram user behind it."""
        return Actor(telegram_user_id=0, display_name=self.WEB_ACTOR_NAME or self.BOT_DISPLAY_NAME)

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
    def newspaper_print_time(self) -> time:
        return time.fromisoformat(self.NEWSPAPER_PRINT_TIME)

    @property
    def hotline_trusted_firm_ids(self) -> frozenset[int]:
        return frozenset(
            int(firm_id.strip()) for firm_id in self.HOTLINE_TRUSTED_FIRM_IDS.split(",") if firm_id.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
