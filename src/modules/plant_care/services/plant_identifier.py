from typing import Protocol

from src.modules.plant_care.domain import PlantIdentification


class PlantIdentifier(Protocol):
    """Reads a photo of an uncatalogued plant and suggests what it is — None when it cannot tell"""

    async def identify(self, photo: bytes) -> PlantIdentification | None:
        ...
