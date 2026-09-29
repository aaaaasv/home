"""The official air-raid map (map.ukrainealarm.com) — a push socket with a polled fallback behind it.

Verified live 25.09.2026 during a real alert. Three things about this feed are not guessable and cost an
evening each:

* **The protocol is the OLD Centrifugo one.** The page loads `centrifuge-js@2.8.5`, so commands are numbered
  methods (`0` connect, `1` subscribe), not the `{"connect": {...}}` shape of the current library. Sending the
  modern shape gets the connection closed with code **3003 and not one word of explanation** — no error frame,
  no reply, just silence and a shut socket.
* **There are two JWTs on the page** and the first one is wrong: `api-token` is for their REST API, while the
  socket needs `centrifugo-token`. Take them by element id, never by "the first thing that looks like a JWT".
* **`updateMap` publishes the whole country every time, not a delta.** Which is convenient — every frame is
  self-sufficient, so a dropped connection cannot mean a missed change.

The fallback matters more here than anywhere else in this project. A socket that is **shut** looks exactly
like calm, and that happened on 25.09 — only a second, independent source revealed it. So `read_current`
prefers the socket **while the connection is open** and polls when it is not.

Trusting silence took one correction to get right. The first rule treated «nothing heard for two minutes» as
stale, which sounds careful and is wrong: the channel publishes only on change, so silence is the normal
state of a quiet night, and the rule made a long alert read from the poll instead — two different services
answering by turns, which is a machine for producing flips. On the night of 29.09 the light came up a second
time at 02:12 and nobody could say which of the two had spoken.

What makes silence trustworthy is not its length but the socket being **open**: `heartbeat=25` has aiohttp
ping the peer and shut the connection when pongs stop, so a dead one stops being open. Silence on an open
socket means «nothing changed»; that is exactly what it is for.

Measured 26.09.2026: the channel sends **no heartbeat of any kind** — ninety seconds of a calm evening
produced not one frame. Which is survivable only because of what it implies: the channel publishes on change,
and the beginning of an alert *is* a change, so the socket talks exactly when it is needed and goes quiet
exactly when it is not. The poll behind it is what turns that quiet from ambiguous into harmless.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import aiohttp

from src.modules.air_alert.domain import AirAlert, AlertLevel

logger = logging.getLogger(__name__)

MAP_URL = "https://map.ukrainealarm.com/"
SOCKET_URL = "wss://ws.ukrainealarm.com/connection/websocket"
FALLBACK_URL = "https://siren.pp.ua/api/v3/alerts"
CHANNEL = "updateMap"

CONNECT_METHOD = 0
SUBSCRIBE_METHOD = 1
REQUEST_TIMEOUT_SECONDS = 15
RECONNECT_DELAY_SECONDS = 5
AIR_ALERT_TYPE = "AIR"
# which of the two answered, kept with every reading so «why did it flip» is a query rather than a guess
SOCKET_SOURCE = "socket"
POLL_SOURCE = "poll"
LEVELS = {"red": AlertLevel.RED, "yellow": AlertLevel.YELLOW}
# a region may carry several levels at once, and which one arrives first is not a fact about the sky
SEVERITY = {AlertLevel.NONE: 0, AlertLevel.YELLOW: 1, AlertLevel.RED: 2}


class UkraineAlarmSource:
    """
    Knows whether there is an alert over one named region, by socket while it can and by poll when it cannot.

    `region_name` is matched exactly as the feed spells it — «м. Київ» is the city and is a different record
    from the surrounding oblast, which is the whole point: an oblast alert with a calm city must not count.
    """

    def __init__(self, region_name: str, session_factory=aiohttp.ClientSession):
        self.region_name = region_name
        self.session_factory = session_factory
        self._alert: AirAlert | None = None
        self._heard_at: datetime | None = None
        self._connected = False

    async def read_current(self) -> AirAlert | None:
        # an open socket that has already told us a level is the better answer; it only goes quiet because
        # nothing changed, and mixing it with the poll by turns is what made the level flip
        if self._connected and self._alert is not None:
            return self._alert.model_copy(update={"source": SOCKET_SOURCE})
        return await self._poll()

    async def run(self, on_change=None) -> None:
        """Holds the socket open forever, reconnecting on its own — started once by the composition root."""
        while True:
            try:
                await self._serve_one_connection(on_change)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("Alert socket dropped: %s: %s", type(error).__name__, error)
            finally:
                # whatever ended it, the poll owns the answer again until a new connection says otherwise
                self._connected = False
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)

    async def _serve_one_connection(self, on_change) -> None:
        async with self.session_factory() as session:
            token = await self._read_token(session)
            async with session.ws_connect(SOCKET_URL, heartbeat=25) as socket:
                await socket.send_str(
                    json.dumps({"id": 1, "method": CONNECT_METHOD, "params": {"token": token, "name": "js"}})
                )
                await socket.send_str(json.dumps({"id": 2, "method": SUBSCRIBE_METHOD, "params": {"channel": CHANNEL}}))
                logger.info("Alert socket connected")
                self._connected = True
                async for message in socket:
                    if message.type is not aiohttp.WSMsgType.TEXT:
                        logger.info("Alert socket closed: %s", message.type)
                        return
                    if self._apply(message.data) and on_change is not None:
                        await on_change()

    async def _read_token(self, session) -> str:
        async with session.get(MAP_URL, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)) as response:
            html = await response.text()
        found = re.search(r'id="centrifugo-token"[^>]*value="([^"]+)"', html)
        if found is None:
            raise ValueError("the map page no longer carries a centrifugo token")
        return found.group(1)

    def _apply(self, frame: str) -> bool:
        """Fold one frame in; answers whether the level for our region actually changed."""
        try:
            payload = json.loads(frame).get("result", {}).get("data")
        except (ValueError, AttributeError):
            return False
        if not isinstance(payload, dict):
            return False
        # a live push nests one level deeper than a recovered publication does
        if "data" in payload:
            payload = payload["data"]
        if not isinstance(payload, dict) or "alerts" not in payload:
            # ping, subscribe reply, anything else — the socket is alive, our region did not move
            return False

        alert = read_region_alert(payload["alerts"], self.region_name)
        self._heard_at = datetime.now(timezone.utc)
        changed = self._alert is None or self._alert.level != alert.level
        self._alert = alert
        return changed

    async def _poll(self) -> AirAlert | None:
        try:
            async with self.session_factory() as session:
                async with session.get(
                    FALLBACK_URL, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
                ) as response:
                    response.raise_for_status()
                    regions = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
            logger.warning("Could not reach the alert fallback: %s", error)
            return None

        if not isinstance(regions, list):
            return None
        return read_region_alert(regions, self.region_name).model_copy(update={"source": POLL_SOURCE})


def read_region_alert(regions: list, region_name: str) -> AirAlert:
    """
    What the feed says about one region. Absence from the list is the all-clear — both endpoints list only
    what is currently alerting.

    **The most severe level wins, not the first one listed.** A region can carry several at once — a drone
    warning and a missile threat are separate entries — and the order they arrive in is the feed's business,
    not a fact about the sky. Reading the first entry made the level flip with the ordering: on the night of
    29.09 the light came up a second time at 02:12 on a «new» red that nobody on the ground had seen.
    """
    worst = AirAlert(level=AlertLevel.NONE)
    for region in regions:
        if not isinstance(region, dict) or region.get("regionName") != region_name:
            continue
        for active in region.get("activeAlerts") or []:
            if active.get("type") != AIR_ALERT_TYPE:
                continue
            for entry in active.get("activeAlertLevels") or []:
                level = LEVELS.get(str(entry.get("alertLevel", "")).lower())
                if level is not None and SEVERITY[level] > SEVERITY[worst.level]:
                    worst = AirAlert(level=level, reason=entry.get("reason") or None, since=_read_moment(entry))
    return worst


def _read_moment(entry: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(str(entry["createdAt"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return None
