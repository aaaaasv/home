"""What the weather digest says, and the thresholds that decide whether a line is worth saying."""

from src.modules.weather.domain import PollenSpecies, VentilationEffect

WEATHER_DIGEST_TITLE = "🌤 <b>Погода</b>"
WEATHER_INDOOR_LINE = "🏠 вдома: {temperature}° · {humidity}%"
WEATHER_OUTDOOR_LINE = "🌍 надворі: {temperature}°, удень до {maximum}°"
WEATHER_OUTDOOR_LINE_WITH_FEELS_LIKE = "🌍 надворі: {temperature}° (відчувається як {feels_like}°), удень до {maximum}°"
WEATHER_WIND_LINE = "💨 {label}"
WEATHER_EVENING_SUFFIX = ", ввечері {temperature}°"
WEATHER_FROST_LINE = "❄️ вночі до {temperature}° — заносьте рослини з балкона"
WEATHER_THUNDERSTORM_LINE = "⛈️ можлива гроза"
WEATHER_UV_LINE = "☀️ УФ високий — крем і кепка"
# the bare fact about outside, not a recommendation — with the 🪟 it already says which way a window would move
# the flat's humidity, and the reader knows if they want that (the plants may want the opposite of comfortable)
WEATHER_VENTILATION_LINES: dict[VentilationEffect, str] = {
    VentilationEffect.DRIER: "🪟 надворі сухіше",
    VentilationEffect.WETTER: "🪟 надворі вологіше",
}
WEATHER_RAIN_LINE = "☔ дощ: {probability}%"
WEATHER_RAIN_LINE_WITH_WINDOW = "☔ дощ: {probability}% — найімовірніше {window}"
WEATHER_RAIN_WINDOW_RANGE = "{start:02d}:00–{end:02d}:00"
WEATHER_RAIN_WINDOW_SINGLE_HOUR = "о {start:02d}:00"
# a low chance of rain is just noise — mention it only when rain is actually plausible
RAIN_NOTABLE_THRESHOLD_PERCENT = 30
WEATHER_AIR_QUALITY_LINE = "🌫 повітря: {label} (AQI {index})"
WEATHER_POLLEN_LINE = "🌾 пилок: {details}"
WEATHER_UNAVAILABLE = "🌤 Погода зараз недоступна."
# a quiet footer that says how fresh the reading is, so an open topic never looks like a morning snapshot
WEATHER_DIGEST_AS_OF = "<i>станом на {time}</i>"
WEATHER_DIGEST_BUTTON_REFRESH = "🔄 Оновити"
WEATHER_DIGEST_REFRESHED = "Оновлено"
# shown at once when 🔄 is tapped, while the forecast is fetched — a status banner, not a blocking wait
WEATHER_DIGEST_REFRESHING = "🔄 оновлюю…"
WEATHER_DIGEST_NOTHING_YET = "Дайджест ще не опубліковано сьогодні"

# european aqi bands: (inclusive upper bound, label) — worst label applies above the last bound
AIR_QUALITY_BANDS: list[tuple[int, str]] = [
    (20, "чудове"),
    (40, "добре"),
    (60, "помірне"),
    (80, "погане"),
    (100, "дуже погане"),
]
AIR_QUALITY_WORST_LABEL = "небезпечне"

# below a fresh breeze nobody would call the day windy, so the line stays absent entirely
WIND_NOTABLE_THRESHOLD_METERS_PER_SECOND = 8.0
# beaufort-ish bands: (inclusive upper bound in m/s, label) — strongest label applies above the last bound
WIND_BANDS: list[tuple[float, str]] = [
    (10.8, "вітряно"),
    (17.2, "сильний вітер"),
]
WIND_STRONGEST_LABEL = "дуже сильний вітер"

# a couple of degrees is not worth a word; humidity in summer and wind in winter push it much further apart
FEELS_LIKE_DIFFERENCE_THRESHOLD_CELSIUS = 3.0

# who advises protection from uv index 3, but at 3 nobody in a flat cares — 6 is where a burn gets quick
UV_INDEX_NOTABLE_THRESHOLD = 6.0
# only worth naming when it threatens what lives on the balcony
FROST_THRESHOLD_CELSIUS = 1.0

POLLEN_SPECIES_LABELS: dict[PollenSpecies, str] = {
    PollenSpecies.RAGWEED: "амброзія",
    PollenSpecies.GRASS: "трава",
    PollenSpecies.BIRCH: "береза",
    PollenSpecies.ALDER: "вільха",
    PollenSpecies.MUGWORT: "полин",
}
# grains/m³ per species: (moderate, high) — below moderate we stay silent, so the digest is quiet out of season
POLLEN_THRESHOLDS: dict[PollenSpecies, tuple[float, float]] = {
    PollenSpecies.RAGWEED: (10, 40),
    PollenSpecies.GRASS: (30, 70),
    PollenSpecies.BIRCH: (10, 90),
    PollenSpecies.ALDER: (10, 90),
    PollenSpecies.MUGWORT: (10, 40),
}
POLLEN_LEVEL_MODERATE = "помірно"
POLLEN_LEVEL_HIGH = "високо"
