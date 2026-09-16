from datetime import date, datetime

from sqlalchemy import func, select, update

from src.infrastructure.db.models import NewspaperIssue
from src.infrastructure.repositories.base import SQLAlchemyRepository


class NewspaperIssueRepository(SQLAlchemyRepository[NewspaperIssue]):
    model = NewspaperIssue

    async def retrieve_for_week(self, week_starts_on: date) -> NewspaperIssue | None:
        result = await self.session.execute(
            select(NewspaperIssue).where(NewspaperIssue.week_starts_on == week_starts_on)
        )
        return result.scalar_one_or_none()

    async def retrieve_last_number(self) -> int | None:
        result = await self.session.execute(select(func.max(NewspaperIssue.number)))
        return result.scalar_one_or_none()

    async def list_recent_answers(self, issue_count: int) -> set[str]:
        result = await self.session.execute(
            select(NewspaperIssue.crossword).order_by(NewspaperIssue.number.desc()).limit(issue_count)
        )
        return {entry["answer"] for crossword in result.scalars() for entry in crossword["entries"]}

    async def mark_printed(self, issue_id: int, printed_at: datetime) -> None:
        await self.session.execute(
            update(NewspaperIssue).where(NewspaperIssue.id == issue_id).values(printed_at=printed_at)
        )
