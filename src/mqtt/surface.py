"""What a module needs to publish its state on the broker and take commands off it.

The second way into this bot that is not telegram, after `src/web/`, and the reason the bot never learns a
word of HomeKit: Homebridge speaks MQTT, Zigbee2MQTT will speak MQTT, and everything meets on the broker.

A module hands over two pure things — a reader that returns what to publish, and a handler that turns one
payload into what to publish next. Neither touches the client, so both can be tested without a broker.
"""
import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

import aiomqtt

from src.common.config import Settings
from src.modules.air_conditioner.services.air_conditioner import AirConditioner

logger = logging.getLogger(__name__)

# a module answers with topic suffix -> payload, and the surface does the publishing
StateReader = Callable[[], Awaitable[Mapping[str, str]]]
CommandHandler = Callable[[str], Awaitable[Mapping[str, str]]]


@dataclass(frozen=True)
class MqttContext:
    """
    What the composition root has built, offered to each module's mqtt entry point.

    a collaborator is None when its module is switched off, so a module reads its settings flag and the
    collaborators it needs and simply registers nothing when they are missing.
    """

    settings: Settings
    air_conditioner: AirConditioner | None = None


class ListenerRegistrar(Protocol):
    """A module's one mqtt entry point: given the surface and what was built, register what it exposes."""

    def __call__(self, surface: "MqttSurface", context: MqttContext) -> None:
        ...


class BrokerClient(Protocol):
    """The part of an mqtt client this surface uses — an async context manager over one connection."""

    async def __aenter__(self) -> "BrokerClient":
        ...

    async def __aexit__(self, *exception: object) -> None:
        ...

    async def subscribe(self, topic: str, qos: int = 0) -> None:
        ...

    async def publish(self, topic: str, payload: bytes, qos: int = 0, retain: bool = False) -> None:
        ...

    @property
    def messages(self) -> AsyncIterator:
        ...


@dataclass(frozen=True)
class _Publication:
    interval_seconds: int
    read: StateReader


class MqttSurface:
    """Holds one broker connection and everything the modules registered on it."""

    def __init__(
        self,
        host: str,
        port: int,
        topic_prefix: str,
        username: str = "",
        password: str = "",
        reconnect_seconds: int = 5,
        client_factory: Callable[["MqttSurface"], BrokerClient] | None = None,
    ):
        self.host = host
        self.port = port
        self.topic_prefix = topic_prefix.rstrip("/")
        self.username = username
        self.password = password
        self.reconnect_seconds = reconnect_seconds
        self.client_factory = client_factory or _build_client
        self._publications: list[_Publication] = []
        self._commands: dict[str, CommandHandler] = {}
        self._farewell: tuple[str, str] | None = None
        self._connection: asyncio.Task | None = None

    def topic(self, suffix: str) -> str:
        return f"{self.topic_prefix}/{suffix}"

    def publish_every(self, interval_seconds: int, read: StateReader) -> None:
        """Publish what this reader returns, on a cadence, for as long as the broker is reachable."""
        self._publications.append(_Publication(interval_seconds=interval_seconds, read=read))

    def on_command(self, suffix: str, handle: CommandHandler) -> None:
        """Call this handler with every payload arriving on the suffix, and publish whatever it returns."""
        self._commands[suffix] = handle

    def announce_loss_as(self, suffix: str, payload: str) -> None:
        """Have the broker publish this the moment the bot stops answering, so no tile is left looking healthy."""
        # mqtt carries one such message per connection, so a second module claiming it would silently
        # take it from the first
        if self._farewell is not None:
            raise RuntimeError("the mqtt farewell message is already claimed by another module")
        self._farewell = (suffix, payload)

    @property
    def farewell(self) -> tuple[str, str] | None:
        return self._farewell

    async def start(self) -> None:
        self._connection = asyncio.create_task(self._serve())

    async def stop(self) -> None:
        if self._connection is None:
            return
        self._connection.cancel()
        try:
            await self._connection
        except asyncio.CancelledError:
            pass
        self._connection = None
        await self._say_farewell()

    async def _say_farewell(self) -> None:
        """Say it on the way out, because the broker only says it for us when the connection breaks."""
        # a deploy is a clean disconnect, so without this a tile would keep showing the last reading —
        # healthy and an hour old — for the whole restart
        if self._farewell is None:
            return

        suffix, payload = self._farewell
        try:
            async with self.client_factory(self) as client:
                await client.publish(self.topic(suffix), payload.encode(), qos=1, retain=True)
        except aiomqtt.MqttError as error:
            logger.warning("Could not announce the mqtt farewell (%s); the broker will do it instead", error)

    async def _serve(self) -> None:
        while True:
            try:
                await self.serve_one_connection()
            except aiomqtt.MqttError as error:
                # the broker being down is an ordinary condition here, not a reason to take the bot with it
                logger.warning("MQTT connection lost (%s)", error)
            # whatever ended the connection, wait before dialling again: a broker that closes the stream
            # without an error would otherwise be reconnected to in a tight loop
            await asyncio.sleep(self.reconnect_seconds)

    async def serve_one_connection(self) -> None:
        """Hold one connection until the broker drops it — reconnecting is the caller's business."""
        async with self.client_factory(self) as client:
            logger.info("MQTT connected to %s:%s as %s", self.host, self.port, self.topic_prefix)
            for suffix in self._commands:
                await client.subscribe(self.topic(suffix), qos=1)
            # publish once on connect, or a controller that just started looks at a blank tile until the
            # first interval elapses
            for publication in self._publications:
                await self._read_and_publish(client, publication)

            publishers = [
                asyncio.create_task(self._publish_loop(client, publication)) for publication in self._publications
            ]
            try:
                async for message in client.messages:
                    await self._receive(client, str(message.topic), message.payload)
            finally:
                for publisher in publishers:
                    publisher.cancel()
                await asyncio.gather(*publishers, return_exceptions=True)

    async def _publish_loop(self, client: BrokerClient, publication: _Publication) -> None:
        while True:
            await asyncio.sleep(publication.interval_seconds)
            await self._read_and_publish(client, publication)

    async def _read_and_publish(self, client: BrokerClient, publication: _Publication) -> None:
        try:
            readings = await publication.read()
        except aiomqtt.MqttError:
            raise
        except Exception:
            # one sensor that cannot be read must not take every other accessory off the broker with it
            logger.exception("An mqtt reader failed; the surface stays up")
            return
        await self._publish(client, readings)

    async def _receive(self, client: BrokerClient, topic: str, payload: bytes) -> None:
        suffix = topic.removeprefix(f"{self.topic_prefix}/")
        handle = self._commands.get(suffix)
        if handle is None:
            return

        # the only way something outside telegram moves real hardware, so it leaves a trace like any other
        logger.info("MQTT command %s = %s", suffix, payload.decode())
        try:
            readings = await handle(payload.decode())
        except Exception:
            logger.exception("An mqtt command failed; the surface stays up")
            return
        await self._publish(client, readings)

    async def _publish(self, client: BrokerClient, readings: Mapping[str, str]) -> None:
        for suffix, payload in readings.items():
            # retained, so a controller starting after the bot sees the current state instead of a blank tile
            await client.publish(self.topic(suffix), payload.encode(), qos=1, retain=True)


def _build_client(surface: MqttSurface) -> BrokerClient:
    will = None
    if surface.farewell is not None:
        suffix, payload = surface.farewell
        will = aiomqtt.Will(surface.topic(suffix), payload.encode(), qos=1, retain=True)
    return aiomqtt.Client(
        hostname=surface.host,
        port=surface.port,
        username=surface.username or None,
        password=surface.password or None,
        identifier=surface.topic_prefix,
        will=will,
    )
