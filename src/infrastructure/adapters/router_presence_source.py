import logging

from asusrouter import AsusData, AsusRouter

from src.modules.presence.domain import NetworkClient

logger = logging.getLogger(__name__)


class RouterPresenceSource:
    """
    Reads the router's client list from its local HTTP API (no cloud).

    it keeps one login and reuses it; on any error it drops the connection so the next read re-logs in, rather than
    hammering the router with a fresh login every few minutes.

    the name is what makes this worth reading rather than just counting addresses: the router learns it over DHCP
    and keeps it for a client that has gone away, so a phone is still recognisable after iOS has rotated the
    private address it wears on this network.
    """

    def __init__(self, host: str, username: str, password: str):
        self._router = AsusRouter(hostname=host, username=username, password=password, use_ssl=False)
        self._connected = False

    async def read_clients(self) -> list[NetworkClient] | None:
        try:
            if not self._connected:
                await self._router.async_connect()
                self._connected = True
            clients = await self._router.async_get_data(AsusData.CLIENTS)
        except Exception as error:  # asusrouter raises a wide range; any of them means "unknown this tick"
            logger.warning("Could not read the client list from the router: %s", error)
            await self._drop_connection()
            return None

        return [_read_client(mac, client) for mac, client in clients.items()]

    async def _drop_connection(self) -> None:
        self._connected = False
        try:
            await self._router.async_disconnect()
        except Exception:
            pass


def _read_client(mac: str, client) -> NetworkClient:
    connection = getattr(client, "connection", None)
    description = getattr(client, "description", None)
    return NetworkClient(
        mac=mac.upper(),
        name=getattr(description, "name", None),
        is_online=bool(connection is not None and getattr(connection, "online", False)),
    )
