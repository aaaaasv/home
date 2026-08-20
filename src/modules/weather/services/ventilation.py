import math

from src.modules.weather.domain import VentilationEffect

# relative humidity does not survive a change of temperature: cold outdoor air at 90% carries less water than
# warm indoor air at 40%, so only the absolute figure says which way opening a window would move the flat
ABSOLUTE_HUMIDITY_DIFFERENCE_THRESHOLD = 3.0
# withhold the drying fact when it is much warmer outside: in the cooling season no one opens up to dry the flat
# by baking it. this guard also stands in for the air conditioner — the indoor sensor already carries whatever the
# compressor is doing to the humidity, so reading the unit's state would add a bind per refresh for no new signal
OUTDOOR_WARMER_TOLERANCE_CELSIUS = 2.0


def absolute_humidity(temperature_celsius: float, relative_humidity_percent: float) -> float:
    """Grams of water vapour per cubic metre (magnus formula)"""
    saturation_pressure = 6.112 * math.exp(17.62 * temperature_celsius / (243.12 + temperature_celsius))
    return 216.7 * (relative_humidity_percent / 100 * saturation_pressure) / (273.15 + temperature_celsius)


def resolve_ventilation_effect(
    indoor_temperature_celsius: float,
    indoor_humidity_percent: float,
    outdoor_temperature_celsius: float,
    outdoor_humidity_percent: float,
) -> VentilationEffect | None:
    """Whether opening the windows would dry the flat or wet it — None when the difference is not worth a line"""
    indoor = absolute_humidity(indoor_temperature_celsius, indoor_humidity_percent)
    outdoor = absolute_humidity(outdoor_temperature_celsius, outdoor_humidity_percent)

    if outdoor > indoor + ABSOLUTE_HUMIDITY_DIFFERENCE_THRESHOLD:
        return VentilationEffect.WETTER
    if outdoor < indoor - ABSOLUTE_HUMIDITY_DIFFERENCE_THRESHOLD:
        if outdoor_temperature_celsius > indoor_temperature_celsius + OUTDOOR_WARMER_TOLERANCE_CELSIUS:
            return None
        return VentilationEffect.DRIER
    return None
