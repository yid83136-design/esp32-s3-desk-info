"""Single-shot SHT3x temperature/humidity reader for MicroPython."""

import time


def crc8(data):
    value = 0xFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ 0x31) & 0xFF if value & 0x80 else (value << 1) & 0xFF
    return value


def read(i2c, address):
    """Return (temperature Celsius, relative humidity percent)."""
    i2c.writeto(address, b'\x24\x00')  # High repeatability, no clock stretching.
    time.sleep_ms(20)
    data = i2c.readfrom(address, 6)
    if crc8(data[:2]) != data[2] or crc8(data[3:5]) != data[5]:
        raise ValueError('SHT3x CRC mismatch')
    raw_temp = (data[0] << 8) | data[1]
    raw_rh = (data[3] << 8) | data[4]
    return -45 + 175 * raw_temp / 65535, 100 * raw_rh / 65535
