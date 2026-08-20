import logging

from asusrouter import AsusData, AsusRouter

logger = logging.getLogger(__name__)


class RouterPresenceSource:
    """
    Reads who is on Wi-Fi from the Asus router's local HTTP API (no cloud).

    it keeps one login and reuses it; on any error it drops the connection so the next poll re-logs in, rather than
    hammering the router with a fresh login every few minutes.
    """

    def __init__(self, host: str, username: str, password: str):
        self._router = AsusRouter(hostname=host, username=username, password=password, use_ssl=False)
        self._connected = False

    async def online_macs(self) -> set[str] | None:
        try:
            if not self._connected:
                await self._router.async_connect()
                self._connected = True
            clients = await self._router.async_get_data(AsusData.CLIENTS)
        except Exception as error:  # asusrouter raises a wide range; any of them means "unknown this tick"
            logger.warning("Could not read presence from the router: %s", error)
            await self._drop_connection()
            return None

        return {mac.upper() for mac, client in clients.items() if _is_online(client)}

    async def _drop_connection(self) -> None:
        self._connected = False
        try:
            await self._router.async_disconnect()
        except Exception:
            pass


def _is_online(client) -> bool:
    connection = getattr(client, "connection", None)
    return bool(connection is not None and getattr(connection, "online", False))
