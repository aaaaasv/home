"""How the weather digest renders."""
from datetime import datetime

from src.bot.handlers.sensors.formatting import render_trend_summary
from src.bot.handlers.weather.messages import (
    AIR_QUALITY_BANDS,
    AIR_QUALITY_WORST_LABEL,
    FEELS_LIKE_DIFFERENCE_THRESHOLD_CELSIUS,
    FROST_THRESHOLD_CELSIUS,
    PM2_5_BANDS,
    POLLEN_LEVEL_HIGH,
    POLLEN_LEVEL_MODERATE,
    POLLEN_SPECIES_LABELS,
    POLLEN_THRESHOLDS,
    RAIN_NOTABLE_THRESHOLD_PERCENT,
    UV_INDEX_NOTABLE_THRESHOLD,
    WEATHER_AIR_QUALITY_LINE,
    WEATHER_AIR_QUALITY_MEASURED,
    WEATHER_DIGEST_AS_OF,
    WEATHER_DIGEST_TITLE,
    WEATHER_EVENING_SUFFIX,
    WEATHER_FROST_WARNING,
    WEATHER_INDOOR_LINE,
    WEATHER_OUTDOOR_LINE,
    WEATHER_OUTDOOR_LINE_WITH_FEELS_LIKE,
    WEATHER_POLLEN_WARNING,
    WEATHER_RAIN_WARNING,
    WEATHER_RAIN_WARNING_WITH_WINDOW,
    WEATHER_RAIN_WINDOW_RANGE,
    WEATHER_RAIN_WINDOW_SINGLE_HOUR,
    WEATHER_THUNDERSTORM_WARNING,
    WEATHER_UNAVAILABLE,
    WEATHER_UV_WARNING,
    WEATHER_VENTILATION_LINES,
    WEATHER_WARNINGS_LINE,
    WEATHER_WARNINGS_SEPARATOR,
    WIND_BANDS,
    WIND_NOTABLE_THRESHOLD_METERS_PER_SECOND,
    WIND_STRONGEST_LABEL,
)
from src.modules.room_climate.domain import RoomClimate
from src.modules.sensors.domain import ClimateTrend
from src.modules.weather.domain import LocalAirQuality, PollenReading, VentilationEffect, WeatherReport


def render_climate_digest(
    indoor: RoomClimate | None,
    outdoor: WeatherReport | None,
    ventilation: VentilationEffect | None = None,
    generated_at: datetime | None = None,
    local_air: LocalAirQuality | None = None,
    trend: ClimateTrend | None = None,
) -> str:
    lines = [WEATHER_DIGEST_TITLE, ""]

    if indoor is not None:
        indoor_line = WEATHER_INDOOR_LINE.format(
            temperature=f"{indoor.temperature_celsius:.0f}", humidity=f"{indoor.relative_humidity_percent:.0f}"
        )
        movement = render_trend_summary(trend) if trend is not None else ""
        lines.append(f"{indoor_line} · {movement}" if movement else indoor_line)

    if outdoor is not None:
        lines.append(_render_outdoor(outdoor))
        warnings = _collect_warnings(outdoor)
        if warnings:
            lines.append(WEATHER_WARNINGS_LINE.format(warnings=WEATHER_WARNINGS_SEPARATOR.join(warnings)))
        # a fact and a measurement rather than something to watch for, so neither is folded into the warnings
        if ventilation is not None:
            lines.append(WEATHER_VENTILATION_LINES[ventilation])
        air_quality_line = _render_air_quality(outdoor, local_air)
        if air_quality_line:
            lines.append(air_quality_line)
    else:
        # say it out loud — an indoor-only digest looks complete, so a silent fetch failure reads as a feature
        lines.append(WEATHER_UNAVAILABLE)

    if generated_at is not None:
        lines.append("")
        lines.append(
            WEATHER_DIGEST_AS_OF.format(unix=int(generated_at.timestamp()), time=generated_at.strftime("%H:%M"))
        )

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


def _collect_warnings(outdoor: WeatherReport) -> list[str]:
    """What is worth knowing about today; each phrase appears only once its own threshold is crossed."""
    warnings = [_render_rain(outdoor)]
    if outdoor.is_thunderstorm_expected:
        warnings.append(WEATHER_THUNDERSTORM_WARNING)
    warnings.append(_render_wind(outdoor))
    if outdoor.uv_index_max is not None and outdoor.uv_index_max >= UV_INDEX_NOTABLE_THRESHOLD:
        warnings.append(WEATHER_UV_WARNING)
    warnings.append(_render_pollen(outdoor.pollen))
    # last, because it is the only phrase that ends in advice
    if outdoor.temperature_min_celsius <= FROST_THRESHOLD_CELSIUS:
        warnings.append(WEATHER_FROST_WARNING.format(temperature=f"{outdoor.temperature_min_celsius:.0f}"))
    return [warning for warning in warnings if warning]


def _render_wind(outdoor: WeatherReport) -> str | None:
    speed = outdoor.wind_speed_meters_per_second
    if speed is None or speed < WIND_NOTABLE_THRESHOLD_METERS_PER_SECOND:
        return None

    label = WIND_STRONGEST_LABEL
    for upper_bound, band_label in WIND_BANDS:
        if speed <= upper_bound:
            label = band_label
            break
    return label


def _render_rain(outdoor: WeatherReport) -> str | None:
    probability = outdoor.precipitation_probability_percent
    if probability is None or probability < RAIN_NOTABLE_THRESHOLD_PERCENT:
        return None

    window = outdoor.rain_window
    if window is None:
        return WEATHER_RAIN_WARNING.format(probability=probability)

    if window.start_hour == window.end_hour:
        rendered_window = WEATHER_RAIN_WINDOW_SINGLE_HOUR.format(start=window.start_hour)
    else:
        rendered_window = WEATHER_RAIN_WINDOW_RANGE.format(start=window.start_hour, end=window.end_hour)
    return WEATHER_RAIN_WARNING_WITH_WINDOW.format(probability=probability, window=rendered_window)


def _render_air_quality(outdoor: WeatherReport, local: LocalAirQuality | None) -> str | None:
    """
    A measurement from three streets away beats a model averaged over eleven kilometres, so it wins when it
    answers. the modelled index stays as the fallback, because volunteer sensors go quiet without notice.
    """
    if local is not None:
        return WEATHER_AIR_QUALITY_MEASURED.format(
            label=_band_label(local.pm2_5_micrograms, PM2_5_BANDS), value=_format_pm2_5(local.pm2_5_micrograms)
        )

    index = outdoor.european_air_quality_index
    if index is None:
        return None
    return WEATHER_AIR_QUALITY_LINE.format(label=_band_label(index, AIR_QUALITY_BANDS), index=index)


def _band_label(value: float, bands: list[tuple[float, str]]) -> str:
    for upper_bound, label in bands:
        if value <= upper_bound:
            return label
    return AIR_QUALITY_WORST_LABEL


def _format_pm2_5(value: float) -> str:
    # a tenth is the honest resolution of these sensors, and whole numbers read as more certain than they are
    return f"{value:.1f}".rstrip("0").rstrip(".")


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
    return WEATHER_POLLEN_WARNING.format(details=", ".join(notable))
