"""How the chores board and deadline card render."""
from datetime import date
from html import escape

from src.bot.formatting import format_day, format_due
from src.bot.handlers.chores.messages import (
    CHORES_BURNING_COUNT,
    CHORES_LIST_EMPTY,
    CHORES_LIST_TITLE,
    CHORES_NOTHING_BURNING,
    CHORES_ONE_BURNING,
    CHORES_SOMEDAY_SECTION,
)
from src.modules.chores.domain import ChoreDetails, ChoreReminder, ChoresList


def render_chores_list(chores: ChoresList, today: date) -> str:
    if chores.is_empty:
        return CHORES_LIST_EMPTY

    burning = sum(1 for chore in chores.dated if (chore.due_on - today).days <= 0)
    lines = [CHORES_LIST_TITLE, _render_heat(burning)]

    if chores.dated:
        lines.append("")
        lines.extend(_render_dated_chore(chore, today) for chore in chores.dated)

    if chores.someday:
        # the dateless pile is collapsed so the deadlines stay in front, and it never speaks on its own
        someday = "\n".join([CHORES_SOMEDAY_SECTION, *(_render_someday_chore(chore) for chore in chores.someday)])
        lines.extend(["", f"<blockquote expandable>{someday}</blockquote>"])

    return "\n".join(lines)


def render_chore_deadline_card(reminder: ChoreReminder) -> str:
    emoji = "🔴" if reminder.days_until_due <= 0 else "📅"
    line = f"{emoji} <b>{escape(reminder.name)}</b> — {format_due(reminder.days_until_due)}"
    if reminder.assignee_telegram_user_id is not None:
        # the card is posted once, so the mention pings the person then and only then — silent edits never re-ping
        line += f" · {_render_mention(reminder.assignee_telegram_user_id, reminder.assignee_display_name)}"
    return line


def _render_mention(telegram_user_id: int, display_name: str | None) -> str:
    label = escape(display_name) if display_name else "👤"
    return f'👤 <a href="tg://user?id={telegram_user_id}">{label}</a>'


def _render_heat(burning: int) -> str:
    if burning == 0:
        return CHORES_NOTHING_BURNING
    if burning == 1:
        return CHORES_ONE_BURNING
    return CHORES_BURNING_COUNT.format(count=burning)


def _render_dated_chore(chore: ChoreDetails, today: date) -> str:
    prefix = "🔴" if (chore.due_on - today).days <= 0 else "📌"
    return f"{prefix} {escape(chore.name)} · {format_day(chore.due_on, today)}{_render_owner(chore)}"


def _render_someday_chore(chore: ChoreDetails) -> str:
    return f"· {escape(chore.name)}{_render_owner(chore)}"


def _render_owner(chore: ChoreDetails) -> str:
    # a plain name on the board, never a tg:// mention — the board edits silently and must not ping anyone
    return f" · 👤 {escape(chore.assignee_display_name)}" if chore.assignee_display_name else ""
