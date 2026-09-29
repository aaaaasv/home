from dataclasses import dataclass

from src.modules.sensors.domain import SensorNow

# a zigbee coin cell falls off a cliff rather than a slope, so twenty is already a few weeks rather than months
BATTERY_ALERT_PERCENT = 20.0
# a fresh cell reads well above this, while a tired one recovering for a moment after a rest does not
BATTERY_RECOVERY_PERCENT = 30.0


@dataclass(frozen=True)
class BatteryVerdict:
    """Which sensors have just run low and deserve a card, and which cards are no longer earned."""

    newly_low: list[SensorNow]
    recovered: set[str]


class SensorBatteryMonitor:
    """
    Decides, from the sensors' latest readings and the cards already standing, who is newly low and who is well again.

    the card is the state: a sensor with a card has been told about, so it is not told about twice, and the card
    goes only once the reading climbs clearly past the threshold — a cell that flickers around twenty must not
    cost the family a fresh message every hour.
    """

    def evaluate(self, readings: list[SensorNow], carded: set[str]) -> BatteryVerdict:
        newly_low = [
            reading
            for reading in readings
            if reading.battery_percent is not None
            and reading.battery_percent < BATTERY_ALERT_PERCENT
            and reading.sensor not in carded
        ]
        still_low = {
            reading.sensor
            for reading in readings
            if reading.battery_percent is not None and reading.battery_percent < BATTERY_RECOVERY_PERCENT
        }
        return BatteryVerdict(newly_low=newly_low, recovered=carded - still_low)
