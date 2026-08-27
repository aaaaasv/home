from typing import Protocol

from src.modules.transit.domain import RouteShape


class RouteShapeCatalog(Protocol):
    """Route geometry from the weekly gtfs-static cache — None when the route has no shape (9К never does)"""

    async def shape_for_route(self, route_id: str) -> RouteShape | None:
        ...

    async def refresh(self) -> None:
        ...
