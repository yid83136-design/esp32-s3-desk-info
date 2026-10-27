"""Four-page desk information display for ESP32-S3 + 128x160 ST7735."""

import gc
import json
import math
import network
import ntptime
import requests
import time
from machine import Pin, SPI, RTC, SoftI2C
from ST7735 import TFT
from font_data import SMALL, CJK, LARGE, MEDIUM
from wifi_config import SSID, PASSWORD
import sht3x

W, H = 128, 160
LAT, LON = 34.25281, 117.25167  # Yunlong, Xuzhou; Open-Meteo geocoder
FORECAST = ('https://api.open-meteo.com/v1/forecast?latitude=34.25281&longitude=117.25167'
            '&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code'
            '&daily=temperature_2m_max,temperature_2m_min,uv_index_max,precipitation_probability_max'
            '&forecast_days=1&timezone=Asia%2FShanghai')
AIR = ('https://air-quality-api.open-meteo.com/v1/air-quality?latitude=34.25281'
       '&longitude=117.25167&current=pm2_5&timezone=Asia%2FShanghai')


def rgb(r, g, b):
    return ((r & 248) << 8) | ((g & 252) << 3) | (b >> 3)


BG = rgb(8, 17, 33)
CARD = rgb(17, 34, 55)
WHITE = rgb(234, 244, 255)
MUTED = rgb(132, 157, 184)
CYAN = rgb(93, 217, 246)
GOLD = rgb(255, 203, 112)
GREEN = rgb(99, 219, 174)
CORAL = rgb(255, 125, 126)


class Canvas:
    def __init__(self):
        self.buf = bytearray(W * H * 2)
        try:
            with open('desk_bg.bin', 'rb') as f:
                self.backgrounds = f.read()
            if len(self.backgrounds) != 4 * W * H * 2:
                self.backgrounds = None
        except OSError:
            self.backgrounds = None

    def rect(self, x, y, w, h, c):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + w), min(H, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        row = bytes((c >> 8, c & 255)) * (x1 - x0)
        for yy in range(y0, y1):
            start = (yy * W + x0) * 2
            self.buf[start:start + len(row)] = row

    def clear(self, page=0):
        if self.backgrounds:
            n = W * H * 2
            self.buf[:] = self.backgrounds[page*n:(page+1)*n]
        else:
            self.buf[:] = bytes((BG >> 8, BG & 255)) * (W * H)

    def text(self, x, y, s, color=WHITE, large=False):
        for ch in str(s):
            if large == 2:
                glyph = MEDIUM.get(ch)
                width, height, advance = 15, 24, 16
            elif large:
                glyph = LARGE.get(ch)
                width, height, advance = 19, 30, 20
            elif ch in CJK:
                glyph = CJK[ch]
                width, height, advance = 12, 14, 13
            else:
                glyph = SMALL.get(ch, SMALL.get('?'))
                width, height, advance = 7, 11, 8
            if glyph:
                stride = (width + 7) // 8
                for yy in range(height):
                    py = y + yy
                    if py < 0 or py >= H:
                        continue
                    for xx in range(width):
                        px = x + xx
                        if 0 <= px < W and (glyph[yy * stride + (xx >> 3)] & (128 >> (xx & 7))):
                            i = (py * W + px) * 2
                            self.buf[i] = color >> 8
                            self.buf[i + 1] = color & 255
            x += advance
        return x


def first(d, key):
    a = d.get(key) or []
    return a[0] if a else None


def fmt(v, suffix='', digits=0):
    if v is None:
        return '--'
    try:
        return (str(round(v, digits)) if digits else str(round(v))) + suffix
    except Exception:
        return '--'


def condition(code):
    if code is None:
        return '待更新'
    if code == 0:
        return '晴'
    if code in (1, 2):
        return '多云'
    if code == 3:
        return '阴'
    if code in (45, 48):
        return '雾'
    if code in (51, 53, 55, 56, 57, 61, 66, 80):
        return '小雨'
    if code in (63, 81):
        return '中雨'
    if code in (65, 67, 82):
        return '大雨'
    if code in (71, 73, 75, 77, 85, 86):
        return '雪'
    if code in (95, 96, 99):
        return '雷雨'
    return '天气'


def local_now():
    return time.localtime(time.time() + 8 * 3600)


MONTHS = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
          'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}


def set_clock_from_http_date(header):
    """Use an HTTPS server's GMT Date header when UDP NTP is unavailable."""
    if not header:
        return False
    if isinstance(header, bytes):
        header = header.decode()
    fields = header.replace(',', '').split()
    if len(fields) < 6 or fields[2] not in MONTHS or fields[5] != 'GMT':
        return False
    hh, mm, ss = [int(v) for v in fields[4].split(':')]
    RTC().datetime((int(fields[3]), MONTHS[fields[2]], int(fields[1]),
                    0, hh, mm, ss, 0))
    return True


class App:
    def __init__(self):
        self.canvas = Canvas()
        self.light = Pin(7, Pin.OUT)
        self.light.off()
        spi = SPI(1, baudrate=1_000_000, polarity=0, phase=0,
                  sck=Pin(12), mosi=Pin(11))
        # TFT constructor order: A0/DC, RESET, CS.
        # Physical wiring: A0=10, RESET=8, CS=9.
        self.screen = TFT(spi, 10, 8, 9)
        self.screen.initr()
        self.screen.rgb(True)
        self.button = Pin(0, Pin.IN, Pin.PULL_UP)
        self.indoor = None
        self.sensor_addr = None
        self.indoor_i2c = SoftI2C(scl=Pin(17), sda=Pin(18), freq=100_000)
        self.next_indoor = time.ticks_ms()
        self.update_indoor()
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.weather = {}
        self.air = {}
        self.updated = None
        self.page = 0
        self.page_at = time.ticks_ms()
        self.next_weather = time.ticks_ms()
        self.next_ntp = time.ticks_ms()
        self.next_wifi = time.ticks_ms()
        self.focus_left = 25 * 60
        self.focus_running = False
        self.last_second = time.ticks_ms()
        self.button_down = None
        self.prev_button = 1
        self.time_ok = False
        print('Display init complete')
        self.load_cache()
        print('Cache loaded; drawing first page')
        self.draw()
        print('First page drawn')
        self.light.on()
        print('Backlight on')

    def load_cache(self):
        try:
            with open('desk_cache.json') as f:
                d = json.load(f)
            self.weather = d.get('weather', {})
            self.air = d.get('air', {})
            self.updated = d.get('updated')
        except Exception:
            pass

    def update_indoor(self):
        try:
            if self.sensor_addr is None:
                addresses = self.indoor_i2c.scan()
                self.sensor_addr = next((a for a in addresses if a in (0x44, 0x45)), None)
                if self.sensor_addr is not None:
                    print('SHT3x found', hex(self.sensor_addr))
            if self.sensor_addr is not None:
                self.indoor = sht3x.read(self.indoor_i2c, self.sensor_addr)
        except Exception as e:
            self.indoor = None
            self.sensor_addr = None
            print('SHT3x:', e)

    def connect(self):
        if self.wlan.isconnected():
            return True
        try:
            self.wlan.connect(SSID, PASSWORD)
            for _ in range(50):
                if self.wlan.isconnected():
                    print('WiFi connected')
                    return True
                time.sleep_ms(100)
        except Exception as e:
            print('WiFi:', e)
        return self.wlan.isconnected()

    def get_json(self, url):
        response = None
        try:
            response = requests.get(url)
            if response.status_code != 200:
                raise ValueError('HTTP ' + str(response.status_code))
            if not self.time_ok:
                try:
                    header = response.headers.get('Date') or response.headers.get('date')
                    if set_clock_from_http_date(header):
                        self.time_ok = True
                        print('Clock synced via HTTPS', local_now()[:6])
                except Exception as e:
                    print('HTTP clock:', e)
            return response.json()
        finally:
            if response:
                response.close()
            gc.collect()

    def refresh(self):
        if not self.wlan.isconnected():
            return
        try:
            data = self.get_json(FORECAST)
            if not data.get('current'):
                raise ValueError('No current weather')
            self.weather = {'current': data['current'], 'daily': data.get('daily', {})}
            self.updated = data['current'].get('time')
            try:
                self.air = self.get_json(AIR).get('current', {})
            except Exception as e:
                print('Air data:', e)
            with open('desk_cache.json', 'w') as f:
                json.dump({'weather': self.weather, 'air': self.air, 'updated': self.updated}, f)
            print('Weather', self.updated, self.weather['current'].get('temperature_2m'),
                  'PM2.5', self.air.get('pm2_5'))
        except Exception as e:
            print('Weather:', e)

    def ntp_sync(self):
        if not self.wlan.isconnected():
            return
        try:
            ntptime.settime()
            self.time_ok = True
            print('Clock synced', local_now()[:6])
        except Exception as e:
            print('NTP:', e)

    def base(self, title, accent):
        c = self.canvas
        c.clear(self.page)
        c.text(9, 12, title, WHITE)
        c.text(81, 12, '云龙区', MUTED)
        for i in range(4):
            c.rect(47 + i * 11, 152, 7, 3, accent if i == self.page else CARD)

    def clock_page(self, now):
        c = self.canvas
        self.base('时钟', CYAN)
        c.text(13, 51, '%02d:%02d' % (now[3], now[4]), WHITE, True)
        c.text(98, 85, '%02d' % now[5], CYAN)
        c.text(17, 93, '%04d-%02d-%02d' % now[:3], MUTED)
        c.text(8, 124, '室内', MUTED)
        if self.indoor is None:
            c.text(36, 124, '--C', GOLD)
            c.text(100, 124, '--%', CYAN)
        else:
            c.text(36, 124, fmt(self.indoor[0], 'C', 1), GOLD)
            humidity_text = fmt(self.indoor[1], '%', 1)
            c.text(124 - 8 * len(humidity_text), 124, humidity_text, CYAN)
        c.rect(73, 15, 4, 4, GREEN if self.wlan.isconnected() else CORAL)

    def weather_page(self):
        c = self.canvas
        self.base('天气', GOLD)
        now = self.weather.get('current', {})
        daily = self.weather.get('daily', {})
        c.text(14, 48, fmt(now.get('temperature_2m')), WHITE, True)
        c.text(57, 70, 'C', GOLD)
        c.text(15, 89, '体感 ' + fmt(now.get('apparent_temperature'), 'C'), MUTED)
        c.text(85, 87, condition(now.get('weather_code')), GOLD)
        c.text(13, 115, '高 ' + fmt(first(daily, 'temperature_2m_max'), 'C'), CORAL)
        c.text(69, 115, '低 ' + fmt(first(daily, 'temperature_2m_min'), 'C'), CYAN)
        c.text(13, 130, '湿度 ' + fmt(now.get('relative_humidity_2m'), '%'), MUTED)

    def tips_page(self):
        c = self.canvas
        self.base('出门', GREEN)
        daily = self.weather.get('daily', {})
        rain = first(daily, 'precipitation_probability_max')
        uv = first(daily, 'uv_index_max')
        pm = self.air.get('pm2_5')
        rows = [('降雨', fmt(rain, '%'), CYAN),
                ('紫外线', fmt(uv, digits=1), GOLD),
                ('PM2.5', fmt(pm), GREEN)]
        for i, (label, value, color) in enumerate(rows):
            y = 37 + i * 32
            c.text(35, y + 8, label, MUTED)
            c.text(88, y + 8, value, color)
        if rain is None and uv is None and pm is None:
            advice = '数据待更新'
        elif rain is not None and rain >= 40:
            advice = '出门带伞'
        elif uv is not None and uv >= 6:
            advice = '注意防晒'
        elif pm is not None and pm >= 75:
            advice = '注意空气'
        else:
            advice = '适合出门'
        c.text(33, 132, advice, WHITE)

    def focus_page(self):
        c = self.canvas
        self.base('专注', CORAL)
        m, s = divmod(self.focus_left, 60)
        done = 25 * 60 - self.focus_left
        for i in range(100 * done // (25 * 60)):
            angle = i * math.pi * 2 / 100 - math.pi / 2
            x = 64 + int(43 * math.cos(angle))
            y = 83 + int(43 * math.sin(angle))
            c.rect(x - 1, y - 1, 3, 3, CORAL)
        c.text(24, 71, '%02d:%02d' % (m, s), WHITE, 2)
        if self.focus_left == 0:
            state = '完成'
        elif self.focus_running:
            state = '专注中'
        else:
            state = '已暂停'
        c.text(44, 103, state, GREEN if self.focus_running else GOLD)
        c.text(18, 133, '长按开始/暂停', MUTED)

    def draw(self):
        now = local_now()
        if self.page == 0:
            self.clock_page(now)
        elif self.page == 1:
            self.weather_page()
        elif self.page == 2:
            self.tips_page()
        else:
            self.focus_page()
        self.screen.image(0, 0, 127, 159, self.canvas.buf)

    def poll_button(self, tick):
        value = self.button.value()
        if value == 0 and self.prev_button == 1:
            self.button_down = tick
        elif value == 1 and self.prev_button == 0 and self.button_down is not None:
            held = time.ticks_diff(tick, self.button_down)
            if held >= 3000:
                self.focus_left = 25 * 60
                self.focus_running = False
                self.page = 3
            elif held >= 800:
                if self.focus_left == 0:
                    self.focus_left = 25 * 60
                self.focus_running = not self.focus_running
                self.page = 3
            elif held >= 40:
                self.page = (self.page + 1) % 4
            self.page_at = tick
            self.draw()
            print('Page', self.page, 'free', gc.mem_free())
            self.button_down = None
        self.prev_button = value

    def run(self):
        print('Desk info starting')
        while True:
            tick = time.ticks_ms()
            self.poll_button(tick)
            if time.ticks_diff(tick, self.next_indoor) >= 0:
                self.next_indoor = time.ticks_add(tick, 5_000)
                self.update_indoor()
                if self.page == 0:
                    self.draw()
            if time.ticks_diff(tick, self.last_second) >= 1000:
                elapsed = time.ticks_diff(tick, self.last_second) // 1000
                self.last_second = tick
                if self.focus_running:
                    self.focus_left = max(0, self.focus_left - elapsed)
                    if self.focus_left == 0:
                        self.focus_running = False
                self.draw()
            if not self.focus_running and time.ticks_diff(tick, self.page_at) >= 7000:
                self.page = (self.page + 1) % 4
                self.page_at = tick
                self.draw()
                print('Page', self.page, 'free', gc.mem_free())
            if time.ticks_diff(tick, self.next_wifi) >= 0:
                self.next_wifi = time.ticks_add(tick, 15000)
                if not self.wlan.isconnected() and self.connect():
                    self.next_weather = tick
                    self.next_ntp = tick
            if self.wlan.isconnected() and time.ticks_diff(tick, self.next_ntp) >= 0:
                self.next_ntp = time.ticks_add(tick, 4 * 3600 * 1000)
                self.ntp_sync()
            if self.wlan.isconnected() and time.ticks_diff(tick, self.next_weather) >= 0:
                self.next_weather = time.ticks_add(tick, 30 * 60 * 1000)
                self.refresh()
                self.draw()
            time.sleep_ms(50)


def run():
    App().run()


if __name__ == '__main__':
    run()
