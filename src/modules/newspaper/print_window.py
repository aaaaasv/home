"""When this week's paper may go to the printer."""
from datetime import datetime, time, timedelta

# retries run from the print time until this much later — from saturday lunchtime into sunday evening
RETRY_WINDOW = timedelta(hours=32)


def find_window_start(local_now: datetime, weekday: int, print_time: time) -> datetime:
    """The latest print moment at or before now, as local wall clock; `weekday` counts monday as 0."""
    days_back = (local_now.weekday() - weekday) % 7
    start = datetime.combine(local_now.date() - timedelta(days=days_back), print_time, tzinfo=local_now.tzinfo)
    if start > local_now:
        start -= timedelta(days=7)
    return start


def is_inside_window(local_now: datetime, weekday: int, print_time: time) -> bool:
    return local_now < find_window_start(local_now, weekday, print_time) + RETRY_WINDOW


def is_last_attempt(local_now: datetime, weekday: int, print_time: time, retry_interval: timedelta) -> bool:
    return local_now + retry_interval >= find_window_start(local_now, weekday, print_time) + RETRY_WINDOW
