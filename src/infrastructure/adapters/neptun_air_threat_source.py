"""The NEPTUN threat map (neptun.in.ua) — an open, unauthenticated feed of what is currently in the air.

Checked live 25.09.2026: `GET /api/v1/threats` answers 200 with no key and no registration. The paths are not
documented anywhere; they were read out of the site's own javascript bundle, so this is somebody else's private
API and it may change or close without notice. Everything here is written to degrade quietly when it does.

Two facts about the payload that the shape does not make obvious, both established by checking real records
against reference coordinates:

* `lat`/`lon` is the **estimated position now**, not the destination — a track named «Кременчук» sat 10.6 km
  from the city centre. `locality` is the nearest named place, and `destination: true` means the tracker presumes
  the thing is heading there.
* `heading` is absent on a large share of records. Nothing may depend on having it.
"""
import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from src.modules.air_threats.domain import AirThreat, ThreatConfidence, ThreatKind

logger = logging.getLogger(__name__)

THREATS_URL = "https://neptun.in.ua/api/v1/threats"
REQUEST_TIMEOUT_SECONDS = 15
# the map's own page identifies itself this way; sending it keeps us recognisable rather than anonymous
REFERER = "https://neptun.in.ua/"
ACTIVE_STATUS = "active"

KINDS = {
    "uav": ThreatKind.UAV,
    "fpv": ThreatKind.FPV,
    "missile": ThreatKind.MISSILE,
    "ballistic": ThreatKind.BALLISTIC,
    "kab": ThreatKind.KAB,
    "aircraft": ThreatKind.AIRCRAFT,
}
CONFIDENCES = {
    "low": ThreatConfidence.LOW,
    "medium": ThreatConfidence.MEDIUM,
    "high": ThreatConfidence.HIGH,
}


class NeptunAirThreatSource:
    """Reads the active tracks — returns None when the map cannot be reached or answers nonsense."""

    def __init__(self, session_factory=aiohttp.ClientSession):
        self.session_factory = session_factory

    async def read_active(self) -> list[AirThreat] | None:
        try:
            payload = await self._fetch()
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            logger.warning("Could not reach the threat map: %s", error)
            return None

        try:
            records = payload["threats"]
        except (KeyError, TypeError):
            logger.warning("The threat map answered something that is not a threat list")
            return None

        threats = []
        for record in records:
            threat = _read_threat(record)
            if threat is not None:
                threats.append(threat)
        return threats

    async def _fetch(self) -> dict:
        async with self.session_factory() as session:
            async with session.get(
                THREATS_URL,
                headers={"Referer": REFERER},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as response:
                response.raise_for_status()
                return await response.json(content_type=None)


def _read_threat(record: dict) -> AirThreat | None:
    """One record, or None — a track without a position says nothing we can use, and an unknown kind is still a kind."""
    try:
        if record.get("status") != ACTIVE_STATUS:
            return None
        latitude = float(record["lat"])
        longitude = float(record["lon"])
        tracker_id = str(record["id"])
    except (KeyError, TypeError, ValueError):
        return None

    return AirThreat(
        tracker_id=tracker_id,
        kind=KINDS.get(str(record.get("type", "")).lower(), ThreatKind.UNKNOWN),
        title=str(record.get("title") or "Ціль"),
        locality=record.get("locality") or None,
        region=record.get("region") or None,
        latitude=latitude,
        longitude=longitude,
        heading_degrees=_optional_number(record.get("heading")),
        confidence=CONFIDENCES.get(str(record.get("confidenceLevel", "")).lower(), ThreatConfidence.LOW),
        source_count=int(record.get("sourceCount") or 0),
        uncertainty_kilometres=_optional_number(record.get("uncertaintyKm")),
        is_position_confirmed=str(record.get("positionQuality", "")).lower() == "confirmed",
        updated_at=_read_moment(record.get("updatedAt")),
    )


def _optional_number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_moment(value) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
