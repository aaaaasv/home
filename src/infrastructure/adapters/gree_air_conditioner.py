import asyncio
import logging

from greeclimate.device import Device
from greeclimate.exceptions import DeviceNotBoundError, DeviceTimeoutError
from greeclimate.network import DeviceInfo

from src.modules.air_conditioner.domain import AirConditionerFanSpeed, AirConditionerMode, AirConditionerState

logger = logging.getLogger(__name__)

PORT = 7000
# the unit answers a status request in about 0.1 s, so poll finely and give up long before a person would
STATE_POLL_INTERVAL_SECONDS = 0.05
STATE_TIMEOUT_SECONDS = 3
READY_TIMEOUT_SECONDS = 3
# a real status reply carries the unit's whole column set; anything written locally is a handful of keys, so the
# key count is what tells a device answer from our own optimistic assignment
FULL_REPLY_MINIMUM_KEYS = 10
# binding back-to-back outruns the unit — one retry after a breath covers a button pressed twice in a row
BIND_ATTEMPTS = 2
BIND_RETRY_DELAY_SECONDS = 0.4
# a healthy bind answers in ~0.1 s; cap it short so a flaky moment fails fast and retries, instead of stalling on
# greeclimate's own multi-second bind timeout (two of those back-to-back is the 15–20 s a stuck tap showed)
BIND_TIMEOUT_SECONDS = 2.5
UNREACHABLE_ERRORS = (OSError, asyncio.TimeoutError, DeviceTimeoutError, DeviceNotBoundError)
# the unit reports its own sensor with a +40 offset, and a bare 0 means this model does not report one at all
ROOM_TEMPERATURE_OFFSET = 40

MODE_CODES: dict[int, AirConditionerMode] = {
    0: AirConditionerMode.AUTO,
    1: AirConditionerMode.COOL,
    2: AirConditionerMode.DRY,
    3: AirConditionerMode.FAN,
    4: AirConditionerMode.HEAT,
}
MODE_VALUES = {mode: code for code, mode in MODE_CODES.items()}

# the unit's WdSpd has six steps; we write four and fold the two in-between steps onto the nearest one we show
FAN_SPEED_VALUES: dict[AirConditionerFanSpeed, int] = {
    AirConditionerFanSpeed.AUTO: 0,
    AirConditionerFanSpeed.LOW: 1,
    AirConditionerFanSpeed.MEDIUM: 3,
    AirConditionerFanSpeed.HIGH: 5,
}
FAN_SPEED_CODES: dict[int, AirConditionerFanSpeed] = {
    0: AirConditionerFanSpeed.AUTO,
    1: AirConditionerFanSpeed.LOW,
    2: AirConditionerFanSpeed.LOW,
    3: AirConditionerFanSpeed.MEDIUM,
    4: AirConditionerFanSpeed.HIGH,
    5: AirConditionerFanSpeed.HIGH,
}


class GreeAirConditioner:
    """
    A gree-protocol indoor unit on the local network — no cloud, no vendor app.

    it binds on every call rather than caching a key: the unit hands out a fresh key each bind, so a stored one
    would go stale. binding normally has to follow a broadcast scan, but the unit answers a unicast bind too,
    which is what lets this work from inside docker's bridge network.
    """

    def __init__(self, host: str, mac: str, name: str):
        self.host = host
        self.mac = mac
        self.name = name
        # the unit serves one client at a time and chokes on binds that arrive back-to-back, so every operation —
        # a button tap or the background poll — takes this lock: concurrent binds collide and time out otherwise
        self._lock = asyncio.Lock()

    @property
    def busy(self) -> bool:
        # a command is mid-flight; the handler drops duplicate taps rather than queueing another behind the lock
        return self._lock.locked()

    async def read_state(self) -> AirConditionerState | None:
        async with self._lock:
            device = await self._connect()
            if device is None:
                return None
            try:
                return self._to_state(await self._read_properties(device))
            finally:
                self._release(device)

    async def apply(
        self,
        is_on: bool | None = None,
        mode: AirConditionerMode | None = None,
        target_temperature_celsius: int | None = None,
        fan_speed: AirConditionerFanSpeed | None = None,
        turbo: bool | None = None,
        quiet: bool | None = None,
        xfan: bool | None = None,
    ) -> AirConditionerState | None:
        async with self._lock:
            device = await self._connect()
            if device is None:
                return None

            try:
                if is_on is not None:
                    device.power = is_on
                if mode is not None:
                    device.mode = MODE_VALUES[mode]
                if target_temperature_celsius is not None:
                    device.target_temperature = target_temperature_celsius
                if fan_speed is not None:
                    device.fan_speed = FAN_SPEED_VALUES[fan_speed]
                if turbo is not None:
                    device.turbo = turbo
                if quiet is not None:
                    device.quiet = quiet
                if xfan is not None:
                    device.xfan = xfan

                try:
                    await device.push_state_update()
                except UNREACHABLE_ERRORS as error:
                    logger.warning("Air conditioner update failed: %r", error)
                    return None

                return self._to_state(await self._read_properties(device))
            finally:
                self._release(device)

    async def _connect(self) -> Device | None:
        for attempt in range(BIND_ATTEMPTS):
            device = Device(DeviceInfo(self.host, PORT, self.mac, self.name))
            connected = False
            try:
                await asyncio.wait_for(device.bind(), timeout=BIND_TIMEOUT_SECONDS)
                try:
                    await asyncio.wait_for(device.ready.wait(), timeout=READY_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    pass
                connected = True
                return device
            except UNREACHABLE_ERRORS as error:
                if attempt + 1 == BIND_ATTEMPTS:
                    logger.warning("Air conditioner unreachable at %s: %r", self.host, error)
                    return None
                await asyncio.sleep(BIND_RETRY_DELAY_SECONDS)
            finally:
                # bind() opens the udp socket before it can fail, so release the device on every path that does not
                # hand it back to the caller — a retry, a give-up, or any unexpected error propagating out. a socket
                # left open is one the gree unit keeps as a live client until it stops answering its own remote
                if not connected:
                    self._release(device)
        return None

    @staticmethod
    def _release(device: Device) -> None:
        # greeclimate never closes its udp transport; left open, every poll leaks a socket the gree unit keeps as
        # a live client, and enough of them make the indoor unit stop answering its own infrared remote
        try:
            device.close()
        except Exception:
            pass

    async def _read_properties(self, device: Device) -> dict:
        # the reply lands on a separate datagram, so the call returns before the properties are populated. wait for
        # a whole column set rather than any content — a property just assigned locally is already "content"
        try:
            await device.update_state()
        except UNREACHABLE_ERRORS as error:
            logger.warning("Air conditioner did not answer a status request: %r", error)
            return {}

        deadline = asyncio.get_running_loop().time() + STATE_TIMEOUT_SECONDS
        while len(device.raw_properties) < FULL_REPLY_MINIMUM_KEYS and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(STATE_POLL_INTERVAL_SECONDS)

        if len(device.raw_properties) < FULL_REPLY_MINIMUM_KEYS:
            logger.warning("Air conditioner did not report its state within %ss", STATE_TIMEOUT_SECONDS)
            return {}
        return device.raw_properties

    def _to_state(self, properties: dict) -> AirConditionerState | None:
        # a half-filled reply means the unit answered something we cannot render — report it as unreachable
        # rather than crashing the handler behind the button
        if not properties or "SetTem" not in properties or "Pow" not in properties:
            return None

        raw_room_temperature = properties.get("TemSen")
        return AirConditionerState(
            is_on=bool(properties.get("Pow")),
            mode=MODE_CODES.get(properties.get("Mod"), AirConditionerMode.AUTO),
            target_temperature_celsius=properties["SetTem"],
            room_temperature_celsius=(raw_room_temperature - ROOM_TEMPERATURE_OFFSET if raw_room_temperature else None),
            fan_speed=FAN_SPEED_CODES.get(properties.get("WdSpd"), AirConditionerFanSpeed.AUTO),
            turbo=bool(properties.get("Tur")),
            # the unit writes 2 for quiet-on and 0 for off, so any truthy value means on
            quiet=bool(properties.get("Quiet")),
            xfan=bool(properties.get("Blo")),
        )
