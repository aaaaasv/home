from src.common.constants import MAXIMUM_CARE_INTERVAL_DAYS, MINIMUM_CARE_INTERVAL_DAYS

# people type any of these between the two numbers of a range: "21-29", "21 – 29", "50—70"
RANGE_SEPARATORS = ("–", "—")


def parse_interval_days(text: str) -> int | None:
    stripped_text = text.strip()
    if not stripped_text.isdigit():
        return None

    interval_days = int(stripped_text)
    if not MINIMUM_CARE_INTERVAL_DAYS <= interval_days <= MAXIMUM_CARE_INTERVAL_DAYS:
        return None
    return interval_days


def parse_climate_range(text: str, minimum: float, maximum: float) -> tuple[float, float] | None:
    normalized = text.strip()
    for separator in RANGE_SEPARATORS:
        normalized = normalized.replace(separator, "-")

    parts = [part.strip() for part in normalized.split("-") if part.strip()]
    if len(parts) != 2:
        return None

    try:
        low = float(parts[0].replace(",", "."))
        high = float(parts[1].replace(",", "."))
    except ValueError:
        return None

    if not (minimum <= low < high <= maximum):
        return None
    return low, high
