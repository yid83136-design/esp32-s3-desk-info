# Optional manual connectivity test; run from the project folder.
import network
from wifi_config import SSID, PASSWORD
w = network.WLAN(network.STA_IF)
w.active(True)
w.connect(SSID, PASSWORD)
print('WiFi status:', w.status())
