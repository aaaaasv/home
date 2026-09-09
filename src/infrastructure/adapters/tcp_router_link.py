import asyncio
import logging

logger = logging.getLogger(__name__)


class TcpRouterLink:
    """
    Asks the router whether it is alive by opening a tcp connection to it and closing it again.

    ping would be the obvious probe and is the wrong one here: icmp from inside a container needs NET_RAW, a
    capability worth far more than this answer. a completed tcp handshake to the admin port proves the same
    thing — the box is up and its network stack is serving — and needs nothing beyond an ordinary socket.
    """

    def __init__(self, host: str, port: int, timeout_seconds: float):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    async def is_alive(self) -> bool:
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout_seconds
            )
        except (OSError, asyncio.TimeoutError) as error:
            logger.info("Router %s:%s did not answer: %s", self.host, self.port, error)
            return False

        writer.close()
        await writer.wait_closed()
        return True
