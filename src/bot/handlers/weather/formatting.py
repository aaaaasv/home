"""How the weather digest renders."""
from datetime import datetime

from src.bot.handlers.weather.messages import (
    AIR_QUALITY_BANDS,
    AIR_QUALITY_WORST_LABEL,
    FEELS_LIKE_DIFFERENCE_THRESHOLD_CELSIUS,
    FROST_THRESHOLD_CELSIUS,
    POLLEN_LEVEL_HIGH,
    POLLEN_LEVEL_MODERATE,
    POLLEN_SPECIES_LABELS,
    POLLEN_THRESHOLDS,
    RAIN_NOTABLE_THRESHOLD_PERCENT,
    UV_INDEX_NOTABLE_THRESHOLD,
    WEATHER_AIR_QUALITY_LINE,
    WEATHER_DIGEST_AS_OF,
    WEATHER_DIGEST_TITLE,
    WEATHER_EVENING_SUFFIX,
    WEATHER_FROST_LINE,
    WEATHER_INDOOR_LINE,
    WEATHER_OUTDOOR_LINE,
    WEATHER_OUTDOOR_LINE_WITH_FEELS_LIKE,
    WEATHER_POLLEN_LINE,
    WEATHER_RAIN_LINE,
    WEATHER_RAIN_LINE_WITH_WINDOW,
    WEATHER_RAIN_WINDOW_RANGE,
    WEATHER_RAIN_WINDOW_SINGLE_HOUR,
    WEATHER_THUNDERSTORM_LINE,
    WEATHER_UNAVAILABLE,
    WEATHER_UV_LINE,
    WEATHER_VENTILATION_LINES,
    WEATHER_WIND_LINE,
    WIND_BANDS,
    WIND_NOTABLE_THRESHOLD_METERS_PER_SECOND,
    WIND_STRONGEST_LABEL,
)
from src.modules.room_climate.domain import RoomClimate
from src.modules.weather.domain import PollenReading, VentilationEffect, WeatherReport


def render_climate_digest(
    indoor: RoomClimate | None,
    outdoor: WeatherReport | None,
    ventilation: VentilationEffect | None = None,
    generated_at: datetime | None = None,
) -> str:
    lines = [WEATHER_DIGEST_TITLE, ""]

    if indoor is not None:
        lines.append(
            WEATHER_INDOOR_LINE.format(
                temperature=f"{indoor.temperature_celsius:.0f}", humidity=f"{indoor.relative_humidity_percent:.0f}"
            )
        )

    if outdoor is not None:
        lines.append(_render_outdoor(outdoor))
        if ventilation is not None:
            lines.append(WEATHER_VENTILATION_LINES[ventilation])
        rain_line = _render_rain(outdoor)
        if rain_line:
            lines.append(rain_line)
        if outdoor.is_thunderstorm_expected:
            lines.append(WEATHER_THUNDERSTORM_LINE)
        wind_line = _render_wind(outdoor)
        if wind_line:
            lines.append(wind_line)
        if outdoor.temperature_min_celsius <= FROST_THRESHOLD_CELSIUS:
            lines.append(WEATHER_FROST_LINE.format(temperature=f"{outdoor.temperature_min_celsius:.0f}"))
        if outdoor.uv_index_max is not None and outdoor.uv_index_max >= UV_INDEX_NOTABLE_THRESHOLD:
            lines.append(WEATHER_UV_LINE)
        air_quality_line = _render_air_quality(outdoor)
        if air_quality_line:
            lines.append(air_quality_line)
        pollen_line = _render_pollen(outdoor.pollen)
        if pollen_line:
            lines.append(pollen_line)
    else:
        # say it out loud — an indoor-only digest looks complete, so a silent fetch failure reads as a feature
        lines.append(WEATHER_UNAVAILABLE)

    if generated_at is not None:
        lines.append("")
        lines.append(WEATHER_DIGEST_AS_OF.format(time=generated_at.strftime("%H:%M")))

    return "\n".join(lines)


def _render_outdoor(outdoor: WeatherReport) -> str:
    temperatures = {
        "temperature": f"{outdoor.temperature_celsius:.0f}",
        "maximum": f"{outdoor.temperature_max_celsius:.0f}",
    }
    apparent = outdoor.apparent_temperature_celsius
    if apparent is None or abs(apparent - outdoor.temperature_celsius) < FEELS_LIKE_DIFFERENCE_THRESHOLD_CELSIUS:
        line = WEATHER_OUTDOOR_LINE.format(**temperatures)
    else:
        line = WEATHER_OUTDOOR_LINE_WITH_FEELS_LIKE.format(feels_like=f"{apparent:.0f}", **temperatures)

    if outdoor.temperature_evening_celsius is not None:
        line += WEATHER_EVENING_SUFFIX.format(temperature=f"{outdoor.temperature_evening_celsius:.0f}")
    return line


def _render_wind(outdoor: WeatherReport) -> str | None:
    speed = outdoor.wind_speed_meters_per_second
    if speed is None or speed < WIND_NOTABLE_THRESHOLD_METERS_PER_SECOND:
        return None

    label = WIND_STRONGEST_LABEL
    for upper_bound, band_label in WIND_BANDS:
        if speed <= upper_bound:
            label = band_label
            break
    return WEATHER_WIND_LINE.format(label=label)


def _render_rain(outdoor: WeatherReport) -> str | None:
    probability = outdoor.precipitation_probability_percent
    if probability is None or probability < RAIN_NOTABLE_THRESHOLD_PERCENT:
        return None

    window = outdoor.rain_window
    if window is None:
        return WEATHER_RAIN_LINE.format(probability=probability)

    if window.start_hour == window.end_hour:
        rendered_window = WEATHER_RAIN_WINDOW_SINGLE_HOUR.format(start=window.start_hour)
    else:
        rendered_window = WEATHER_RAIN_WINDOW_RANGE.format(start=window.start_hour, end=window.end_hour)
    return WEATHER_RAIN_LINE_WITH_WINDOW.format(probability=probability, window=rendered_window)


def _render_air_quality(outdoor: WeatherReport) -> str | None:
    index = outdoor.european_air_quality_index
    if index is None:
        return None

    label = AIR_QUALITY_WORST_LABEL
    for upper_bound, band_label in AIR_QUALITY_BANDS:
        if index <= upper_bound:
            label = band_label
            break
    return WEATHER_AIR_QUALITY_LINE.format(label=label, index=index)


def _render_pollen(readings: list[PollenReading]) -> str | None:
    notable = []
    for reading in readings:
        moderate_threshold, high_threshold = POLLEN_THRESHOLDS[reading.species]
        if reading.grains_per_cubic_meter < moderate_threshold:
            continue
        level = POLLEN_LEVEL_HIGH if reading.grains_per_cubic_meter >= high_threshold else POLLEN_LEVEL_MODERATE
        notable.append(f"{POLLEN_SPECIES_LABELS[reading.species]} {level}")

    if not notable:
        return None
    return WEATHER_POLLEN_LINE.format(details=", ".join(notable))
