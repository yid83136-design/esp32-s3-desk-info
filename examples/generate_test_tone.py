"""Generate a short, speech-free stereo PCM sample for voice.py."""

import math
import struct
from pathlib import Path

rate = 16000
seconds = 1
amplitude = 3500
output = Path(__file__).resolve().parent / "test_tone.pcm"
with output.open("wb") as stream:
    for index in range(rate * seconds):
        sample = round(amplitude * math.sin(2 * math.pi * 440 * index / rate))
        stream.write(struct.pack("<hh", sample, sample))
print(output)
