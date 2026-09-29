"""Fine-grained timeline: when exactly does the shop close after a card tap?"""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def shop_open(gray):
    return bool(b.vis.find(gray, "shop_close", 0.80))

# open shop -> Buildings&Traps -> Resources
img, gray = b.grab()
if not shop_open(gray):
    m = b.vis.find(gray, "shop_button", 0.70)
    b.adb.tap(m[0], m[1], 2); time.sleep(2.0)
b.adb.tap(316, 65, 3); time.sleep(1.1)
b.adb.tap(525, 221, 3); time.sleep(1.1)
img, gray = b.grab()
print("shop open (verified):", shop_open(gray))

print("-- idle 3s control (no taps) --")
for i in range(3):
    time.sleep(1.0)
    img, gray = b.grab()
    print(f"   idle {i+1}s: shop_open={shop_open(gray)}")

print("-- tap card3 art at (759,430), poll every ~0.2s --")
b.adb.tap(759, 430, 2)
t0 = time.time()
for i in range(10):
    img, gray = b.grab()
    print(f"   t+{time.time()-t0:.2f}s shop_open={shop_open(gray)}")
    time.sleep(0.2)
