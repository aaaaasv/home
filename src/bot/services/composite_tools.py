"""Several toolboxes handed to the assistant as one, so a module can offer tools without the assistant knowing it."""
import logging
from collections.abc import Sequence
from typing import Any

from src.infrastructure.adapters.claude_language_model import HouseholdToolbox

logger = logging.getLogger(__name__)


class CompositeTools:
    """
    One toolbox made of many, assembled in the composition root the way the routers and the jobs already are.

    without it a module's tools would have to be written into the assistant's own file, and adding a module
    would mean editing it again — the god-file the rest of this layer was taken apart to avoid.
    """

    def __init__(self, toolsets: Sequence[HouseholdToolbox]):
        self.toolsets = toolsets

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return [definition for toolset in self.toolsets for definition in toolset.definitions]

    async def run(self, name: str, arguments: dict[str, Any]) -> str:
        for toolset in self.toolsets:
            if any(definition["name"] == name for definition in toolset.definitions):
                return await toolset.run(name, arguments)
        logger.warning("The assistant asked for a tool no toolset offers: %s", name)
        return "Такого інструмента немає."
