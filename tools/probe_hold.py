"""Test press-and-hold (3s, 1px drag) pickup on a shop card."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def info(tag):
    img, gray = b.grab()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    d = {"shop": bool(b.vis.find(gray, "shop_close", 0.80)),
         "home": bool(b.vis.find(gray, "attack_button", 0.78)),
         "attack_v": int(hsv[620, 90][2]),
         "res": b.vis.read_village_resources(img)}
    print(f"  [{tag}] shop={d['shop']} home={d['home']} attack_v={d['attack_v']} res={d['res']}")
    return img, d

img, d = info("start")
if d["attack_v"] == 128:
    b.adb.keyevent(4); time.sleep(1.0); img, d = info("left editor")

# open shop + Resources
b.adb.tap(1207, 656, 2); time.sleep(2.0)
img, d = info("shop")
if not d["shop"]:
    print("shop did not open"); sys.exit(1)
b.adb.tap(316, 65, 3); time.sleep(1.1)
b.adb.tap(525, 221, 3); time.sleep(1.1)
img, gray = b.grab()
print("  Resources landmark:", b.vis.find_near(gray, "price_gold", 476, 596, 28, 0.70))

print("HOLD 3s on card3 art (759,430) with 1px drag")
b.adb.swipe(759, 430, 760, 430, ms=3000)
img, d = info("immediately")
time.sleep(1.5)
img2, d2 = info("1.5s later")

print("HOLD 3s on card3 PRICE (759,596) — reopen shop first")
if not d2["shop"]:
    b.adb.tap(1207, 656, 2); time.sleep(2.0)
    b.adb.tap(316, 65, 3); time.sleep(1.1)
    b.adb.tap(525, 221, 3); time.sleep(1.1)
    img, gray = b.grab()
    print("  shop:", bool(b.vis.find(gray, "shop_close", 0.80)),
          "landmark:", b.vis.find_near(gray, "price_gold", 476, 596, 28, 0.70))
b.adb.swipe(759, 596, 760, 596, ms=3000)
img, d = info("immediately")
time.sleep(1.5)
img2, d2 = info("1.5s later")
