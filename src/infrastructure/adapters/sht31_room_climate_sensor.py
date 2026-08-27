import asyncio
import logging
import time

from smbus2 import SMBus, i2c_msg

from src.modules.room_climate.domain import RoomClimate

logger = logging.getLogger(__name__)

# single shot, high repeatability, clock stretching DISABLED. the broadcom i2c block on every raspberry pi
# implements clock stretching incorrectly, so 0x2C06 — the command every arduino tutorial shows — corrupts transfers
MEASURE_WITHOUT_CLOCK_STRETCHING = [0x24, 0x00]

# datasheet: a high repeatability measurement takes at most 15.5 ms
MEASUREMENT_DURATION_SECONDS = 0.025

CRC_POLYNOMIAL = 0x31
CRC_INITIAL_VALUE = 0xFF


class Sht31RoomClimateSensor:
    """Reads a sensirion SHT3x over i2c — every value is crc-protected, so a bad wire cannot fake a plausible number"""

    def __init__(self, bus_number: int, address: int):
        self.bus_number = bus_number
        self.address = address
        # one physical bus, and smbus2 is not thread safe
        self.bus_lock = asyncio.Lock()

    async def read(self) -> RoomClimate | None:
        async with self.bus_lock:
            try:
                payload = await asyncio.to_thread(self._read_payload)
            except OSError as error:
                logger.warning("SHT31 is not answering on the bus: %s", error)
                return None

        if not self._is_payload_intact(payload):
            logger.warning("SHT31 returned a corrupt reading — check the wiring, not the code")
            return None

        return RoomClimate(
            temperature_celsius=-45.0 + 175.0 * (payload[0] << 8 | payload[1]) / 65535.0,
            relative_humidity_percent=100.0 * (payload[3] << 8 | payload[4]) / 65535.0,
        )

    def _read_payload(self) -> bytes:
        # opened per read: a transient bus fault must not leave a poisoned file descriptor behind forever
        with SMBus(self.bus_number) as bus:
            bus.i2c_rdwr(i2c_msg.write(self.address, MEASURE_WITHOUT_CLOCK_STRETCHING))
            time.sleep(MEASUREMENT_DURATION_SECONDS)
            reading = i2c_msg.read(self.address, 6)
            bus.i2c_rdwr(reading)
            return bytes(reading)

    def _is_payload_intact(self, payload: bytes) -> bool:
        return self._checksum(payload[0:2]) == payload[2] and self._checksum(payload[3:5]) == payload[5]

    def _checksum(self, word: bytes) -> int:
        checksum = CRC_INITIAL_VALUE
        for byte in word:
            checksum ^= byte
            for _ in range(8):
                is_high_bit_set = checksum & 0x80
                checksum = (checksum << 1) & 0xFF
                if is_high_bit_set:
                    checksum ^= CRC_POLYNOMIAL
        return checksum
