from datetime import datetime

from src.common.domain import DomainModel
from src.infrastructure.db.models import Place
from src.modules.places.constants import PlaceSetting


class PlaceDetails(DomainModel):
    id: int
    name: str
    link: str | None
    address: str | None
    note: str | None
    setting: PlaceSetting | None
    added_by_display_name: str
    visited_at: datetime | None
    visited_by_display_name: str | None

    @classmethod
    def from_place(cls, place: Place) -> "PlaceDetails":
        return cls(
            id=place.id,
            name=place.name,
            link=place.link,
            address=place.address,
            note=place.note,
            setting=PlaceSetting(place.setting) if place.setting else None,
            added_by_display_name=place.added_by_display_name,
            visited_at=place.visited_at,
            visited_by_display_name=place.visited_by_display_name,
        )

    @property
    def is_visited(self) -> bool:
        return self.visited_at is not None


class PlacesList(DomainModel):
    to_visit: list[PlaceDetails]
    visited: list[PlaceDetails]

    @classmethod
    def from_places(cls, places: list[Place]) -> "PlacesList":
        details = [PlaceDetails.from_place(place) for place in places]
        return cls(
            to_visit=[place for place in details if not place.is_visited],
            # newest visit first, so the history reads as a recent memory rather than an archive
            visited=sorted(
                (place for place in details if place.is_visited), key=lambda place: place.visited_at, reverse=True
            ),
        )

    @property
    def is_empty(self) -> bool:
        return not self.to_visit and not self.visited
