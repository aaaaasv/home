from src.common.domain import DomainModel


class PanelLightState(DomainModel):
    """What the strip beside the switchboard is doing, as the host service reports it"""

    is_on: bool
    brightness_percent: float
