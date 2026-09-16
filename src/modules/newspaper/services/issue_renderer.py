from datetime import date
from typing import Protocol

from src.modules.newspaper.domain import NewspaperIssue


class IssueRenderer(Protocol):
    """Lays an issue out as a printable document."""

    def render(self, issue: NewspaperIssue, printed_on: date) -> bytes:
        ...
