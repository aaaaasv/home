"""How the places list renders."""
from html import escape

from src.bot.handlers.places.messages import PLACES_LIST_EMPTY, PLACES_LIST_TITLE, PLACES_VISITED_SECTION
from src.modules.places.domain import PlaceDetails, PlacesList


def render_places_list(places: PlacesList) -> str:
    if places.is_empty:
        return PLACES_LIST_EMPTY

    lines = [PLACES_LIST_TITLE]
    if places.to_visit:
        lines.append("")
        lines.extend(_render_place(place) for place in places.to_visit)

    if places.visited:
        # the history of where the family has been, collapsed so the still-to-go list stays in front
        visited = "\n".join([PLACES_VISITED_SECTION, *(_render_visited_place(place) for place in places.visited)])
        lines.extend(["", f"<blockquote expandable>{visited}</blockquote>"])

    return "\n".join(lines)


def _render_place(place: PlaceDetails) -> str:
    name = f'<a href="{escape(place.link)}">{escape(place.name)}</a>' if place.link else escape(place.name)
    return f"📍 {name} · {escape(place.added_by_display_name)}"


def _render_visited_place(place: PlaceDetails) -> str:
    name = f'<a href="{escape(place.link)}">{escape(place.name)}</a>' if place.link else escape(place.name)
    return f"✓ {name} · {escape(place.visited_by_display_name)}"
