"""Turns the journal of alert levels into facts a model can answer from."""
from src.bot.handlers.air_alert.messages import (
    AIR_ALERT_FACTS_LEVELS,
    AIR_ALERT_FACTS_SOURCES,
    AIR_ALERT_FACTS_TITLE,
    AIR_ALERT_FACTS_TRANSITIONS,
)
from src.bot.services.household_facts import FactsContext
from src.common.household_calendar import HouseholdCalendar
from src.modules.air_alert.domain import AlertJournalEntry
from src.modules.air_alert.use_cases.list_recent_air_alerts import ListRecentAirAlertsUseCase

# a week covers «коли остання тривога вночі», and the journal keeps far more for anyone who wants the log itself
RECENT_DAYS = 7
RECENT_ENTRY_LIMIT = 40


async def gather_facts(context: FactsContext) -> str:
    """The last week of level changes, each with why the feed gave it and which feed it came from."""
    entries = await ListRecentAirAlertsUseCase(
        uow=context.uow_factory(), household_calendar=context.household_calendar
    )(days=RECENT_DAYS, limit=RECENT_ENTRY_LIMIT)
    return render_air_alert_facts(entries, context.household_calendar)


def render_air_alert_facts(entries: list[AlertJournalEntry], calendar: HouseholdCalendar) -> str:
    if not entries:
        return ""
    lines = [AIR_ALERT_FACTS_TITLE]
    lines.extend(_describe(entry, calendar) for entry in entries)
    return "\n".join(lines)


def _describe(entry: AlertJournalEntry, calendar: HouseholdCalendar) -> str:
    moment = f"{calendar.local_date(entry.at).isoformat()} {calendar.local_time(entry.at):%H:%M}"
    details = [
        AIR_ALERT_FACTS_TRANSITIONS[entry.transition],
        entry.reason or "",
        AIR_ALERT_FACTS_SOURCES.get(entry.source or "", ""),
    ]
    suffix = ", ".join(detail for detail in details if detail)
    return f"— {moment}: {AIR_ALERT_FACTS_LEVELS[entry.level]}" + (f" ({suffix})" if suffix else "")
