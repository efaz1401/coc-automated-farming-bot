"""Deterministic in-shop probe (assumes the shop may already be open)."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def snap():
    img, gray = b.grab()
    close = b.vis.find(gray, "shop_close", 0.80)
    return img, gray, close

def green_blobs(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    strip = hsv[560:720]
    hh, ss, vv = strip[:, :, 0], strip[:, :, 1], strip[:, :, 2]
    m = ((hh > 50) & (hh < 85) & (ss > 130) & (vv > 150)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [(int(cv2.contourArea(c)), (lambda r: (r[0], r[1] + 560, r[2], r[3]))(cv2.boundingRect(c)))
            for c in cnts if cv2.contourArea(c) > 800]

img, gray, close = snap()
print("shop open at start:", bool(close), close)
if not close:
    m = b.vis.find(gray, "shop_button", 0.70)
    print("shop_button:", m)
    if m:
        b.adb.tap(m[0], m[1], 2); time.sleep(2.2)
        img, gray, close = snap()
        print("shop opened:", bool(close))

# Buildings & Traps tab
b.adb.tap(316, 65, 3); time.sleep(1.3)
# Resources sub-tab
b.adb.tap(525, 221, 3); time.sleep(1.3)
img, gray, close = snap()
cv2.imwrite("logs/p3_res.png", img)
print("in shop:", bool(close), "| price_gold near card2:", b.vis.find_near(gray, "price_gold", 476, 596, 28, 0.70))
print("green blobs on Resources tab:", green_blobs(img))

# tap Gold Mine price button (3rd card) — should be 150 elixir
b.adb.tap(759, 588, 2)
for i in range(8):
    time.sleep(0.6)
    img2, gray2, close2 = snap()
    print(f"  t+{0.6*(i+1):.1f}s shop_close={bool(close2)} green_blobs={green_blobs(img2)}")
    if i in (1, 3):
        cv2.imwrite(f"logs/p3_after_tap_{i}.png", img2)
    if not close2 and i > 1:
        cv2.imwrite("logs/p3_placement_mode.png", img2)
        break
print("resources:", b.vis.read_village_resources(b.grab()[0]))
