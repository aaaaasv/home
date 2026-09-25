from pydantic import BaseModel, Field


class TrackAirThreatsCommand(BaseModel):
    """Where we are, and how close or how pointed at us a thing has to be before it is worth a message."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # anything at all this close is worth knowing about — "Київ і околиці"
    near_kilometres: float = Field(gt=0)
    # and beyond that, only what is actually pointed at us, and only the kinds that cross such a distance
    approach_degrees: float = Field(gt=0, le=180)
    inbound_kinds: frozenset[str]
