import shutil
from pathlib import Path

from src.modules.system_health.domain import PiHealthReading

THERMAL_ZONE_PATH = Path("/sys/class/thermal/thermal_zone0/temp")
HWMON_ROOT = Path("/sys/class/hwmon")
UNDERVOLTAGE_DRIVER_NAME = "rpi_volt"


class SysfsPiHealthSensor:
    """
    Reads the pi's vitals straight from sysfs, so it works from inside the container with no vcgencmd and no device
    mounts: temperature from the thermal zone, under-voltage from the rpi_volt hwmon alarm, disk from the data volume
    (a bind mount of the host's sd card).
    """

    def __init__(self, data_path: str):
        self.data_path = data_path

    async def read(self) -> PiHealthReading | None:
        temperature_celsius = self._read_temperature_celsius()
        if temperature_celsius is None:
            return None
        return PiHealthReading(
            temperature_celsius=temperature_celsius,
            is_undervoltage=self._read_undervoltage(),
            disk_used_percent=self._read_disk_used_percent(),
        )

    def _read_temperature_celsius(self) -> float | None:
        try:
            return int(THERMAL_ZONE_PATH.read_text().strip()) / 1000
        except OSError:
            return None

    def _read_undervoltage(self) -> bool:
        # the hwmon index is not stable across boots, so match by driver name rather than a fixed hwmonN
        for hwmon in HWMON_ROOT.glob("hwmon*"):
            try:
                if (hwmon / "name").read_text().strip() != UNDERVOLTAGE_DRIVER_NAME:
                    continue
                return (hwmon / "in0_lcrit_alarm").read_text().strip() == "1"
            except OSError:
                continue
        return False

    def _read_disk_used_percent(self) -> float:
        usage = shutil.disk_usage(self.data_path)
        return usage.used / usage.total * 100
