"""The NEPTUN threat map as a push channel rather than a poll — `wss://neptun.in.ua/api/v1/stream`.

Polling cost more warning than it was worth: at ballistic speed a thirty-second interval is twenty kilometres
of flight, and at Mach 5 it is fifty-one — three quarters of everything a seventy-kilometre radius could have
given. The socket removes that whole delay; what is left upstream (an observer seeing a thing, writing it down,
the map fusing it) is minutes we cannot touch, which is exactly why the part we can touch must not be wasted.

Frames observed live 25.09.2026:

* `snapshot` — the whole list, sent on connect. `data.threats` is the same record shape the REST path returns.
* `upsert`  — one track, sent the moment it changes. `data` is that record.
* `remove`  — a track that is gone; carries its id.
* `alerts`  — air-raid state per raion with `level` red/yellow, ignored here (another module's business).
* `heartbeat` — roughly every five seconds, which is also how a dead connection is told from a quiet one.
"""
import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable

import aiohttp

from src.infrastructure.adapters.neptun_air_threat_source import read_threat
from src.modules.air_threats.domain import AirThreat

logger = logging.getLogger(__name__)

STREAM_URL = "wss://neptun.in.ua/api/v1/stream"
ORIGIN = "https://neptun.in.ua"
# the map heartbeats about every five seconds, so silence for this long means the connection is dead, not calm
SILENCE_TIMEOUT_SECONDS = 30
RECONNECT_DELAY_SECONDS = 5


class NeptunAirThreatStream:
    """
    Holds what is currently in the air, kept fresh by a socket, and tells the caller the moment it changes.

    it is also an `AirThreatSource`: `read_active()` answers from memory, so the rule that decides what is worth
    a message stays exactly as it was and keeps its tests. the socket only makes the answer current.
    """

    def __init__(self, on_change: Callable[[], Awaitable[None]] | None = None):
        self.on_change = on_change
        self._threats: dict[str, AirThreat] = {}
        self._connected = False

    async def read_active(self) -> list[AirThreat] | None:
        # never connected yet is not the same as "nothing is flying", and must not close every open card
        if not self._connected:
            return None
        return list(self._threats.values())

    async def run(self, session_factory=aiohttp.ClientSession) -> None:
        """Holds the socket open forever, reconnecting on its own — started once by the composition root."""
        while True:
            try:
                await self._serve_one_connection(session_factory)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("Threat stream dropped: %s: %s", type(error).__name__, error)
            self._connected = False
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)

    async def _serve_one_connection(self, session_factory) -> None:
        async with session_factory() as session:
            async with session.ws_connect(STREAM_URL, headers={"Origin": ORIGIN}, heartbeat=25) as socket:
                logger.info("Threat stream connected")
                while True:
                    message = await asyncio.wait_for(socket.receive(), timeout=SILENCE_TIMEOUT_SECONDS)
                    if message.type is not aiohttp.WSMsgType.TEXT:
                        logger.info("Threat stream closed: %s", message.type)
                        return
                    if await self._apply(message.data) and self.on_change is not None:
                        await self._notify()

    async def _apply(self, frame: str) -> bool:
        """Fold one frame into what we hold; answers whether anything a person would care about moved."""
        try:
            message = json.loads(frame)
            kind = message.get("type")
            payload = message.get("data") or {}
        except (ValueError, AttributeError):
            return False

        if kind == "snapshot":
            self._threats = {
                threat.tracker_id: threat
                for threat in (read_threat(record) for record in payload.get("threats", []))
                if threat is not None
            }
            self._connected = True
            return True

        if kind == "upsert":
            threat = read_threat(payload)
            if threat is None:
                # a record that stopped being active arrives as an upsert too, so it leaves the same way
                self._threats.pop(str(payload.get("id", "")), None)
                return True
            self._threats[threat.tracker_id] = threat
            return True

        if kind == "remove":
            removed = str(payload.get("id") or message.get("id") or "")
            return self._threats.pop(removed, None) is not None

        # heartbeat, alerts, and whatever they add next — the connection is alive, nothing here moved
        return False

    async def _notify(self) -> None:
        try:
            await self.on_change()
        except Exception:
            # one bad card must not take the socket down with it
            logger.exception("Reacting to a threat change failed; the stream stays up")


@contextlib.asynccontextmanager
async def running_stream(stream: NeptunAirThreatStream):
    """Keeps the socket task tied to the caller's lifetime, so shutdown does not leave it orphaned."""
    task = asyncio.create_task(stream.run())
    try:
        yield stream
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
