"""What the power module says about the station, the schedule and conservation."""


# ⚡ Світло — the EcoFlow Delta 2 card. read cache-first, so it opens instantly; a scan only runs on cold start
# or a manual refresh, and the placeholder covers that wait
POWER_ECOFLOW_TITLE = "🔋 <b>Delta 2</b>"
POWER_ECOFLOW_READING = "🔋 читаю Delta 2…"
POWER_ECOFLOW_ON_MAINS = "🔌 від мережі"
POWER_ECOFLOW_ON_MAINS_CHARGING = "🔌 від мережі · заряджається {watts} Вт"
POWER_ECOFLOW_ON_BATTERY = "🪫 на батареї"
POWER_ECOFLOW_TIME_TO_FULL = "до повного ~{duration}"
POWER_ECOFLOW_TIME_LEFT = "лишилось ~{duration}"
POWER_ECOFLOW_OUTPUT = "⚡ віддає {watts} Вт"
POWER_ECOFLOW_AS_OF = "<i>станом на {time}</i>"
POWER_ECOFLOW_UNREACHABLE = "🔋 Delta 2 не відповідає — увімкнена й поряд?"
POWER_ECOFLOW_CARD_EXPIRED = "Готово, але ця картка застаріла — надішли /eco"
POWER_ECOFLOW_REFRESHED = "Оновлено"
# each button names the end state it brings about, decided when the card is drawn, so a stale tap can't toggle back
POWER_ECOFLOW_BUTTON_AC_ON = "🔌 Розетки увімкнути"
POWER_ECOFLOW_BUTTON_AC_OFF = "🔌 Розетки вимкнути"
POWER_ECOFLOW_BUTTON_USB_ON = "USB увімкнути"
POWER_ECOFLOW_BUTTON_USB_OFF = "USB вимкнути"
POWER_ECOFLOW_BUTTON_DC_ON = "DC 12В увімкнути"
POWER_ECOFLOW_BUTTON_DC_OFF = "DC 12В вимкнути"
POWER_ECOFLOW_BUTTON_REFRESH = "🔄 Оновити"
# shown the instant a slow ble button is tapped, so it does not feel dead during the ~15s round-trip
POWER_ECOFLOW_WORKING_TOAST = "🔄 читаю Delta 2…"

# /conserve — the storage-regime control card. a rare, once-in-months action, so it earns its own command rather
# than a button that hangs on every /eco card
POWER_CONSERVATION_IN_USE = "▶️ <b>Delta 2</b> — у користуванні"
POWER_CONSERVATION_IN_USE_PERCENT = "▶️ <b>Delta 2</b> — у користуванні (~{percent}%)"
POWER_CONSERVATION_STORED = "🗄 <b>Delta 2</b> — на зберіганні (~{percent}%)"
POWER_CONSERVATION_BUTTON_STORE = "🗄 Позначити на зберігання"
POWER_CONSERVATION_BUTTON_IN_USE = "▶️ Позначити у користуванні"
POWER_CONSERVATION_STORED_TOAST = "🗄 Delta 2 на зберіганні"
POWER_CONSERVATION_IN_USE_TOAST = "▶️ Delta 2 у користуванні"

# ⚡ Світло — Yasno outage schedule. the daily digest is self-editing and silent (a glance, never a ping) like the
# weather digest; the pushes below (pre-outage, emergency) are the only notifications, and carry facts, not advice
POWER_SCHEDULE_TITLE = "🗓 <b>Графік відключень</b> — сьогодні"
POWER_SCHEDULE_INTERVAL = "🕯 {start}–{end}"
POWER_SCHEDULE_EMERGENCY_NOTE = "⚠️ аварійні відключення"
POWER_SCHEDULE_AS_OF = "<i>станом на {time}</i>"
POWER_SCHEDULE_BUTTON_REFRESH = "🔄 Оновити"
POWER_SCHEDULE_REFRESHED = "Оновлено"
POWER_SCHEDULE_REFRESHING = "🔄 оновлюю…"
# a bare fact, no nudge — the design forbids "charge your phone" style advice
POWER_OUTAGE_SOON = "⚡ За {minutes} хв планове відключення {start}–{end}"
POWER_OUTAGE_EMERGENCY = "⚠️ Аварійні відключення у вашій групі — світло можуть вимкнути будь-коли"

# ⚡ Світло — EcoFlow conservation regime, fires only while the station is shelved/off. silent unless action is
# needed; the warranty line nags daily. the pure logic returns a structured advisory, mapped to these here
POWER_CONSERVATION_STORE_RED = "🔴 <b>Delta 2</b> — на зберіганні, ~{estimated}% · ціль {target}%"
POWER_CONSERVATION_STORE_YELLOW = "🟡 <b>Delta 2</b> — на зберіганні, ~{estimated}% · ціль {target}%"
POWER_CONSERVATION_STORE_BLUE = "🔵 <b>Delta 2</b> — на зберіганні, ~{estimated}% · ціль {target}%"
POWER_CONSERVATION_STORE_GREEN = "🟢 <b>Delta 2</b> — на зберіганні, ~{estimated}% · ціль {target}%"
POWER_CONSERVATION_CYCLE_SOON = "🟢 <b>Delta 2</b> — калібрувальний цикл за ~{days} дн"
POWER_CONSERVATION_CYCLE_DUE = "🟡 <b>Delta 2</b> — час калібрувального циклу (60→0→100→60)"
POWER_CONSERVATION_WARRANTY = "🔴 <b>Delta 2</b> — {days} дн до втрати гарантії без циклу (60→0→100→60)"
