import logging
import statistics

import aiohttp

from src.modules.weather.domain import LocalAirQuality

logger = logging.getLogger(__name__)

FILTER_URL = "https://data.sensor.community/airrohr/v1/filter/area={latitude},{longitude},{radius}"
# the sds011 reports pm10 as P1 and pm2.5 as P2
PM2_5_KEY = "P2"
# a stuck or unplugged sensor reports absurd numbers; anything outside this is not air, it is a fault
PLAUSIBLE_MAXIMUM = 2000.0


class SensorCommunityAirQuality:
    """
    Reads PM2.5 from the hobby sensors nearby, because the modelled index cannot see this street.

    the endpoint returns the last five minutes, several rows per sensor, so this takes the newest row from
    each and then the median across sensors. a median rather than a mean on purpose: these are cheap optical
    units that over-read badly in high humidity, and one of them being wrong is ordinary rather than unusual.
    """

    def __init__(self, latitude: float, longitude: float, radius_km: float, timeout_seconds: float):
        self.url = FILTER_URL.format(latitude=latitude, longitude=longitude, radius=radius_km)
        self.timeout_seconds = timeout_seconds

    async def read(self) -> LocalAirQuality | None:
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.url) as response:
                    response.raise_for_status()
                    rows = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            # a volunteer network going quiet is normal; the modelled index stands in
            logger.info("Local air sensors did not answer: %s", error)
            return None

        newest = self._newest_per_sensor(rows)
        readings = sorted(value for value in (self._pm2_5(row) for row in newest) if value is not None)
        if not readings:
            logger.info("Local air sensors answered with no usable pm2.5")
            return None
        return LocalAirQuality(pm2_5_micrograms=statistics.median(readings), sensor_count=len(readings))

    def _newest_per_sensor(self, rows: list) -> list[dict]:
        newest: dict[int, dict] = {}
        for row in rows:
            try:
                sensor_id = row["sensor"]["id"]
                timestamp = row["timestamp"]
            except (KeyError, TypeError):
                continue
            if sensor_id not in newest or timestamp > newest[sensor_id]["timestamp"]:
                newest[sensor_id] = row
        return list(newest.values())

    def _pm2_5(self, row: dict) -> float | None:
        for measurement in row.get("sensordatavalues", []):
            if measurement.get("value_type") != PM2_5_KEY:
                continue
            try:
                value = float(measurement["value"])
            except (KeyError, TypeError, ValueError):
                return None
            return value if 0 <= value <= PLAUSIBLE_MAXIMUM else None
        return None
