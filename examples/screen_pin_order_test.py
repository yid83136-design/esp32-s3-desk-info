"""Temporary ST7735 test for the actual board-2 wiring.

Display: LED=7, SCK=12, SDA=11, A0=10, RESET=8, CS=9.
Run with mpremote; do not install as main.py.
"""

import time
from machine import Pin, SPI
from ST7735 import TFT


light = Pin(7, Pin.OUT)
light.off()
spi = SPI(1, baudrate=1_000_000, polarity=0, phase=0,
          sck=Pin(12), mosi=Pin(11))
# TFT arguments are (spi, A0/DC, RESET, CS), not (spi, CS, A0, RESET).
screen = TFT(spi, 10, 8, 9)
screen.initr()
screen.rgb(True)
screen.fill(TFT.RED)
light.on()
print("RED 10 seconds")
time.sleep(10)
screen.fill(TFT.GREEN)
print("GREEN 10 seconds")
time.sleep(10)
screen.fill(TFT.BLUE)
print("BLUE 10 seconds")
time.sleep(10)
print("Pin-order screen test finished")
