from datetime import datetime

from src.common.domain import DomainModel


class EcoFlowState(DomainModel):
    """A Delta 2 snapshot read over local ble — as_of stamps when, since it may be a cached reading"""

    battery_percent: float
    # ac input watts above zero means the station is charging from the wall — the interim "mains present" signal
    on_mains: bool
    ac_input_power: int
    ac_output_power: int
    ac_output_on: bool
    usb_output_on: bool
    dc_output_on: bool
    # minutes to full while on mains, minutes of runtime left while on battery — None until the station reports it
    remaining_minutes: int | None
    charge_limit_max: int | None
    backup_reserve_percent: int | None
    cell_temperature_celsius: int | None
    as_of: datetime
