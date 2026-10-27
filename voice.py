"""Play 16 kHz signed 16-bit stereo PCM through the MAX98357A on board 2."""

import time
from machine import I2S, Pin


def play(path='hello_2.pcm'):
    enable = Pin(14, Pin.OUT, value=1)
    speaker = None
    try:
        speaker = I2S(0, sck=Pin(4), ws=Pin(5), sd=Pin(6),
                      mode=I2S.TX, bits=16, format=I2S.STEREO,
                      rate=16000, ibuf=16384)
        with open(path, 'rb') as sound:
            while True:
                block = sound.read(4096)
                if not block:
                    break
                offset = 0
                while offset < len(block):
                    written = speaker.write(block[offset:])
                    if written is None or written <= 0:
                        raise OSError('I2S write failed')
                    offset += written
        time.sleep_ms(350)
    finally:
        if speaker is not None:
            speaker.deinit()
        enable.value(0)
