#!/usr/bin/env python3
"""Live read the SHT31 climate sensor straight off the i2c bus, bypassing the bot.

Meant for hardware checks on the pi, not for production. Run it with no arguments to
stream a read every second until Ctrl-C, or pass --once for a single read:

    python3 scripts/read_climate.py            # live stream, Ctrl-C to stop
    python3 scripts/read_climate.py --once      # one read and exit
    python3 scripts/read_climate.py --count 20  # twenty reads then exit

Occasional CRC failures while the bot is running are expected and harmless: both this
script and the container talk to the same bus, and a collided transaction is caught by
the checksum and simply retried on the next tick.
"""
import argparse
import os
import sys
import time

from smbus2 import SMBus, i2c_msg

I2C_BUS = int(os.environ.get("CLIMATE_SENSOR_I2C_BUS", "1"))
I2C_ADDRESS = int(os.environ.get("CLIMATE_SENSOR_I2C_ADDRESS", str(0x44)))
# high repeatability, clock stretching disabled — broadcom's i2c hardware breaks stretching on every pi
MEASURE_COMMAND = [0x24, 0x00]


def crc8(data: bytes) -> int:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def read_once(bus: SMBus) -> tuple[float, float]:
    bus.i2c_rdwr(i2c_msg.write(I2C_ADDRESS, MEASURE_COMMAND))
    time.sleep(0.02)
    read = i2c_msg.read(I2C_ADDRESS, 6)
    bus.i2c_rdwr(read)
    payload = bytes(read)

    temperature_raw, temperature_crc = payload[0:2], payload[2]
    humidity_raw, humidity_crc = payload[3:5], payload[5]
    if crc8(temperature_raw) != temperature_crc or crc8(humidity_raw) != humidity_crc:
        raise ValueError(f"crc mismatch: {payload.hex()}")

    temperature = -45 + 175 * (int.from_bytes(temperature_raw, "big") / 65535)
    humidity = 100 * (int.from_bytes(humidity_raw, "big") / 65535)
    return temperature, humidity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="take a single read and exit")
    parser.add_argument("--count", type=int, default=0, help="stop after this many reads (0 = run until Ctrl-C)")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between reads")
    arguments = parser.parse_args()

    # flush every line as it happens, so reads stream live even when stdout is piped through ssh
    sys.stdout.reconfigure(line_buffering=True)

    limit = 1 if arguments.once else arguments.count
    print(f"reading sht31 at bus {I2C_BUS}, address {hex(I2C_ADDRESS)} — Ctrl-C to stop")
    taken = 0
    with SMBus(I2C_BUS) as bus:
        try:
            while limit == 0 or taken < limit:
                stamp = time.strftime("%H:%M:%S")
                try:
                    temperature, humidity = read_once(bus)
                    print(f"{stamp}  🌡 {temperature:5.2f} °C   💧 {humidity:4.1f} %RH")
                except Exception as error:
                    print(f"{stamp}  read failed -> {error!r}")
                taken += 1
                if limit == 0 or taken < limit:
                    time.sleep(arguments.interval)
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
