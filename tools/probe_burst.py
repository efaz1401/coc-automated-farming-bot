"""Burst-capture frames immediately after a shop card tap to catch the
transition (dim/placement state may last <1s)."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def info(gray=None, img=None, tag=""):
    if img is None:
        img, gray = b.grab()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return {"shop": bool(b.vis.find(gray, "shop_close", 0.80)),
            "attack_v": int(hsv[620, 90][2]),
            "center": hsv[360, 640].tolist()}

img, gray = b.grab()
d = info(gray=gray, img=img, tag="start")
print("start:", d)
if d["attack_v"] == 128:
    b.adb.keyevent(4); time.sleep(1.0)
if not d["shop"]:
    b.adb.tap(1207, 656, 2); time.sleep(2.0)
b.adb.tap(316, 65, 3); time.sleep(1.1)
b.adb.tap(525, 221, 3); time.sleep(1.1)
img, gray = b.grab()
print("shop verified:", bool(b.vis.find(gray, "shop_close", 0.80)),
      "| landmark:", b.vis.find_near(gray, "price_gold", 476, 596, 28, 0.70))
cv2.imwrite("logs/burst_before.png", img)

print("tap card3 art -> burst capture")
b.adb.tap(759, 430, 2)
frames = []
t0 = time.time()
for i in range(8):
    img, gray = b.grab()
    frames.append((time.time() - t0, img.copy(), info(gray=gray, img=img)))
for t, img, d in frames:
    print(f"  t+{t:.2f}s shop={d['shop']} attack_v={d['attack_v']} center={d['center']}")
for i in (0, 1, 2):
    cv2.imwrite(f"logs/burst_{i}.png", frames[i][1])
print("saved burst_0..2")
