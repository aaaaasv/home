"""Turns the household to-do list into facts a model can answer from."""
from src.bot.services.household_facts import FactsContext
from src.modules.chores.domain import ChoreDetails, ChoresList
from src.modules.chores.use_cases.retrieve_chores import RetrieveChoresUseCase


async def gather_facts(context: FactsContext) -> str:
    """The list as it stands — a finished chore is already out of it."""
    return render_chores_facts(await RetrieveChoresUseCase(uow=context.uow_factory())())


def render_chores_facts(chores: ChoresList) -> str:
    if chores.is_empty:
        return ""
    lines = ["Незроблені домашні справи:"]
    lines.extend(f"— {chore.name}: до {chore.due_on.isoformat()}{_render_assignee(chore)}" for chore in chores.dated)
    lines.extend(f"— {chore.name}: без дати{_render_assignee(chore)}" for chore in chores.someday)
    return "\n".join(lines)


def _render_assignee(chore: ChoreDetails) -> str:
    return f", на {chore.assignee_display_name}" if chore.assignee_display_name else ""
