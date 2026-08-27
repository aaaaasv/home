from src.common.domain import DomainModel


class RoomClimate(DomainModel):
    """The air of the room itself. Plants subscribe to it, the air conditioner acts on it, the digest reports it"""

    temperature_celsius: float
    relative_humidity_percent: float
