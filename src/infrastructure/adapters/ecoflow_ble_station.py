import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from src.modules.power.domain import EcoFlowState
from src.vendor.eflib import NewDevice
from src.vendor.eflib.devicebase import DeviceBase

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 30
# the ems state-of-charge only lands after the crypto handshake completes and the first heartbeat arrives, so its
# presence is what separates a live, authenticated link from a bare socket that connected but never spoke
POPULATE_TIMEOUT_SECONDS = 15
POLL_INTERVAL_SECONDS = 0.5
# a breath after the soc lands, so the inverter and pd heartbeats can fill the port and power fields too
POPULATE_SETTLE_SECONDS = 2
# a control command is echoed back in the next heartbeat — wait for it so the snapshot shows the confirmed state
CONTROL_SETTLE_SECONDS = 2
# how often the maintainer checks the link and, if it is down, tries to rebuild it from a fresh scan
MAINTAIN_INTERVAL_SECONDS = 30


class EcoFlowBleStation:
    """
    The EcoFlow Delta 2 over local ble, spoken through the vendored eflib protocol, held open the way the library
    is meant to be used: a background maintainer connects once and keeps the link alive, so reads and control just
    snapshot the live in-memory state instead of paying a ~15s scan+connect each time.

    eflib's own auto-reconnect is disabled — this class owns reconnection, rebuilding from a fresh scan whenever the
    link drops, which also covers the station being powered off and back on (its advertisement reappears). the
    single ble central slot means the phone app cannot use ble while this holds the link; in practice the app talks
    over WiFi when the station is on WiFi, so they do not contend. a link that stays down is the station being off
    or stored — the signal the conservation tracker reads (as a stale last-seen time, so a brief drop is not that).
    """

    def __init__(
        self,
        user_id: str,
        ble_mac: str,
        timezone: ZoneInfo,
        scan_seconds: int = 12,
    ) -> None:
        self._user_id = user_id
        self._ble_mac = ble_mac.upper()
        self._timezone = timezone
        self._scan_seconds = scan_seconds
        # one control op at a time; reads are lock-free snapshots of the live device
        self._lock = asyncio.Lock()
        self._device: DeviceBase | None = None
        self._maintain_task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        # launch the background maintainer; it establishes and keeps the link, so the first /eco need not wait on ble
        if self._maintain_task is None:
            self._stopping = False
            self._maintain_task = asyncio.create_task(self._maintain())

    async def stop(self) -> None:
        self._stopping = True
        if self._maintain_task is not None:
            self._maintain_task.cancel()
            try:
                await self._maintain_task
            except asyncio.CancelledError:
                pass
            self._maintain_task = None
        if self._device is not None:
            await self._release(self._device)
            self._device = None

    async def read_state(self, refresh: bool = False) -> EcoFlowState | None:
        # instant: the link is held open and the props update from heartbeats, so a snapshot is always current
        device = self._device
        if device is None or not device.is_connected:
            return None
        return self._snapshot(device)

    async def apply(
        self,
        ac_output: bool | None = None,
        usb_output: bool | None = None,
        dc_output: bool | None = None,
        charge_limit_max: int | None = None,
    ) -> EcoFlowState | None:
        async with self._lock:
            device = self._device
            if device is None or not device.is_connected:
                return None
            try:
                if ac_output is not None:
                    await device.enable_ac_ports(ac_output)
                if usb_output is not None:
                    await device.enable_usb_ports(usb_output)
                if dc_output is not None:
                    await device.enable_dc_12v_port(dc_output)
                if charge_limit_max is not None:
                    await device.set_battery_charge_limit_max(float(charge_limit_max))
                await asyncio.sleep(CONTROL_SETTLE_SECONDS)
                return self._snapshot(device)
            except Exception as error:
                logger.warning("EcoFlow control failed: %r", error)
                return None

    async def _maintain(self) -> None:
        while not self._stopping:
            try:
                await self._ensure_connected()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("EcoFlow maintainer error: %r", error)
            await asyncio.sleep(MAINTAIN_INTERVAL_SECONDS)

    async def _ensure_connected(self) -> None:
        device = self._device
        if device is not None and device.is_connected:
            return
        # a dropped link → tear it down and rebuild from a fresh scan (this class owns reconnection)
        if device is not None:
            await self._release(device)
            self._device = None
        self._device = await self._establish()

    async def _establish(self) -> DeviceBase | None:
        device = await self._scan()
        if device is None:
            logger.info("EcoFlow Delta 2 not seen on ble (off, stored, or out of range)")
            return None
        # own reconnection here rather than letting eflib race us with its own
        device.with_disabled_reconnect(True)
        try:
            await device.connect(user_id=self._user_id)
            await device.wait_connected(timeout=CONNECT_TIMEOUT_SECONDS)
        except Exception as error:
            logger.warning("EcoFlow ble connect failed: %r", error)
            await self._release(device)
            return None
        if not await self._wait_populated(device):
            logger.warning("EcoFlow connected but reported no state within %ss", POPULATE_TIMEOUT_SECONDS)
            await self._release(device)
            return None
        logger.info("EcoFlow ble link up (%s%%)", round(device.battery_level or 0))
        return device

    async def _scan(self) -> DeviceBase | None:
        holder: dict[str, DeviceBase] = {}

        def on_advertisement(ble_device: BLEDevice, advertisement: AdvertisementData) -> None:
            if ble_device.address.upper() != self._ble_mac or "device" in holder:
                return
            # NewDevice reads the serial out of the manufacturer advertisement, so it needs the adv, not just the mac
            device = NewDevice(ble_device, advertisement)
            if device is not None:
                holder["device"] = device

        scanner = BleakScanner(detection_callback=on_advertisement)
        await scanner.start()
        try:
            deadline = asyncio.get_running_loop().time() + self._scan_seconds
            while "device" not in holder and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
        finally:
            await scanner.stop()
        return holder.get("device")

    async def _wait_populated(self, device: DeviceBase) -> bool:
        deadline = asyncio.get_running_loop().time() + POPULATE_TIMEOUT_SECONDS
        while device.battery_level is None and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        if device.battery_level is None:
            return False
        await asyncio.sleep(POPULATE_SETTLE_SECONDS)
        return True

    def _snapshot(self, device: DeviceBase) -> EcoFlowState | None:
        battery = device.battery_level
        if battery is None:
            return None
        ac_input_power = int(device.ac_input_power or 0)
        on_mains = ac_input_power > 0
        remaining = device.remaining_time_charging if on_mains else device.remaining_time_discharging
        cell_temperature = device.cell_temperature
        return EcoFlowState(
            battery_percent=round(battery, 1),
            on_mains=on_mains,
            ac_input_power=ac_input_power,
            ac_output_power=int(device.ac_output_power or 0),
            ac_output_on=bool(device.ac_ports),
            usb_output_on=bool(device.usb_ports),
            dc_output_on=bool(device.dc_12v_port),
            remaining_minutes=int(remaining) if remaining is not None else None,
            charge_limit_max=device.battery_charge_limit_max,
            backup_reserve_percent=device.energy_backup_battery_level,
            cell_temperature_celsius=round(cell_temperature) if cell_temperature is not None else None,
            as_of=datetime.now(self._timezone),
        )

    @staticmethod
    async def _release(device: DeviceBase) -> None:
        try:
            await device.disconnect()
        except Exception:
            pass
