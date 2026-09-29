"""Turns the log of phones joining and leaving into facts a model can answer from."""
from src.bot.handlers.presence.messages import PRESENCE_FACTS_EVENTS, PRESENCE_FACTS_OUTCOMES, PRESENCE_FACTS_TITLE
from src.bot.services.household_facts import FactsContext
from src.common.household_calendar import HouseholdCalendar
from src.modules.presence.domain import PresenceLogEntry
from src.modules.presence.use_cases.list_recent_presence import ListRecentPresenceUseCase

# «вчора» and «позавчора» are what gets asked; older than that is a question for the log itself
RECENT_DAYS = 3
# a phone hopping between bands writes a row every few seconds, so the tail is what stays worth reading
RECENT_ENTRY_LIMIT = 80


async def gather_facts(context: FactsContext) -> str:
    """The last few days of arrivals and departures, with what the welcome light made of each arrival."""
    entries = await ListRecentPresenceUseCase(uow=context.uow_factory(), household_calendar=context.household_calendar)(
        days=RECENT_DAYS, limit=RECENT_ENTRY_LIMIT
    )
    return render_presence_facts(entries, context.household_calendar)


def render_presence_facts(entries: list[PresenceLogEntry], calendar: HouseholdCalendar) -> str:
    if not entries:
        return ""
    lines = [PRESENCE_FACTS_TITLE]
    lines.extend(_describe(entry, calendar) for entry in entries)
    return "\n".join(lines)


def _describe(entry: PresenceLogEntry, calendar: HouseholdCalendar) -> str:
    moment = f"{calendar.local_date(entry.at).isoformat()} {calendar.local_time(entry.at):%H:%M}"
    line = f"— {moment}: телефон {entry.phone_number} {PRESENCE_FACTS_EVENTS[entry.event]}"
    if entry.outcome is not None:
        line += f" ({PRESENCE_FACTS_OUTCOMES[entry.outcome]})"
    return line
