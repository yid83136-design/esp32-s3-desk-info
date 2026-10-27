"""Read I2S microphone levels without saving or transmitting audio."""

import struct
from machine import I2S, Pin


def sample_levels():
    microphone = I2S(1, sck=Pin(15), ws=Pin(16), sd=Pin(21),
                     mode=I2S.RX, bits=32, format=I2S.STEREO,
                     rate=16000, ibuf=20000)
    buffer = bytearray(4096)
    try:
        for window in range(1, 7):
            peak = 0
            total = 0
            count = 0
            nonzero = 0
            right_peak = 0
            for _ in range(25):
                length = microphone.readinto(buffer)
                if not length:
                    continue
                for offset in range(0, length - 7, 8):
                    # L/R is grounded, so the microphone uses the left slot.
                    value = struct.unpack_from('<i', buffer, offset)[0] >> 8
                    magnitude = abs(value)
                    if magnitude > peak:
                        peak = magnitude
                    total += magnitude
                    nonzero += magnitude != 0
                    right = abs(struct.unpack_from('<i', buffer, offset + 4)[0] >> 8)
                    if right > right_peak:
                        right_peak = right
                    count += 1
            print('window', window, 'samples', count,
                  'mean_abs', total // count if count else 0,
                  'peak', peak, 'nonzero', nonzero,
                  'right_peak', right_peak)
    finally:
        microphone.deinit()


if __name__ == '__main__':
    sample_levels()
