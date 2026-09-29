"""Test touch mapping in the shop card area + double-tap buy attempt."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def info():
    img, gray = b.grab()
    return {
        "shop": bool(b.vis.find(gray, "shop_close", 0.80)),
        "home": bool(b.vis.find(gray, "attack_button", 0.78)),
        "attack_v": cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[620, 90][2],
        "res": b.vis.read_village_resources(img),
    }

def open_res_tab():
    img, gray = b.grab()
    if not b.vis.find(gray, "shop_close", 0.80):
        m = b.vis.find(gray, "shop_button", 0.70)
        if m:
            b.adb.tap(m[0], m[1], 2); time.sleep(2.0)
    b.adb.tap(316, 65, 3); time.sleep(1.1)
    b.adb.tap(525, 221, 3); time.sleep(1.1)
    # verify Resources tab via the Elixir Collector gold price icon
    img, gray = b.grab()
    return b.vis.find_near(gray, "price_gold", 476, 596, 28, 0.70)

print("Resources tab landmark:", open_res_tab())

# TEST A: info button of card 2 (Elixir Collector) at (585, 286)
print("--- TEST A: tap card2 info button (585,286) ---")
b.adb.tap(585, 286, 2)
time.sleep(1.4)
imgA, grayA = b.grab()
cv2.imwrite("logs/map_A_info.png", imgA)
print("  shop_open:", bool(b.vis.find(grayA, "shop_close", 0.80)),
      "| center px:", cv2.cvtColor(imgA, cv2.COLOR_BGR2HSV)[360, 640].tolist())

# TEST B: double-tap the price button of card 2 (gold coin price = 150 gold)
print("--- TEST B: double-tap card2 price button (476,596) ---")
b.adb.tap(476, 596, 2)
time.sleep(0.18)
b.adb.tap(476, 596, 2)
time.sleep(1.5)
imgB, grayB = b.grab()
cv2.imwrite("logs/map_B_dblprice.png", imgB)
print("  ", info())

# TEST C: reopen and try tapping the card art twice
print("--- TEST C: reopen + double-tap card2 art (462,430) ---")
print("  landmark:", open_res_tab())
b.adb.tap(462, 430, 2)
time.sleep(0.18)
b.adb.tap(462, 430, 2)
time.sleep(1.5)
imgC, grayC = b.grab()
cv2.imwrite("logs/map_C_dblart.png", imgC)
print("  ", info())
