from typing import Protocol


class PrintQueue(Protocol):
    """A printer that takes a finished pdf."""

    async def print_document(self, document: bytes, job_name: str) -> bool:
        """True only once the printer reports the page done — a job that was merely accepted is not a print."""
        ...
