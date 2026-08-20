from src.bot.handlers.places.formatting import render_places_list
from src.bot.handlers.places.keyboards import build_places_list_keyboard
from src.bot.services.posted_message_tracker import PLACES_LIST_KIND
from src.bot.services.single_message_board import SingleMessageBoard
from src.modules.places.domain import PlacesList

PLACES_MODULE_NAME = "places"


class PlacesBoard(SingleMessageBoard):
    """The single self-editing message the places list lives in, reposted once Telegram's 48h window closes."""

    kind = PLACES_LIST_KIND

    def render(self, places: PlacesList) -> str:
        return render_places_list(places)

    def build_keyboard(self, places: PlacesList):
        return build_places_list_keyboard(places)
