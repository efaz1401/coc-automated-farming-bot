"""Rigorous drag-pickup test: drag from shop card to map, watch dim state."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def st(tag=""):
    img, gray = b.grab()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    d = {
        "shop": bool(b.vis.find(gray, "shop_close", 0.80)),
        "home": bool(b.vis.find(gray, "attack_button", 0.78)),
        "attack_v": int(hsv[620, 90][2]),
        "center": hsv[360, 640].tolist(),
        "res": b.vis.read_village_resources(img),
    }
    print(f"  [{tag}] shop={d['shop']} home={d['home']} attack_v={d['attack_v']} center={d['center']} res={d['res']}")
    return img, d

print("A. ensure HOME")
img, d = st("start")
if not d["home"]:
    b.adb.keyevent(4); time.sleep(1.2)   # leave editor if stuck
    img, d = st("after back")
if d["attack_v"] == 128:
    b.adb.keyevent(4); time.sleep(1.2)
    img, d = st("left editor")

print("B. open shop + Resources (verified)")
b.adb.tap(1207, 656, 2); time.sleep(2.0)
img, d = st("shop")
assert d["shop"], "shop failed to open - aborting"
b.adb.tap(316, 65, 3); time.sleep(1.1)
b.adb.tap(525, 221, 3); time.sleep(1.1)
img, gray = b.grab()
landmark = b.vis.find_near(gray, "price_gold", 476, 596, 28, 0.70)
print("   Resources-tab landmark:", landmark)
assert landmark, "Resources tab not verified - aborting"

print("C. DRAG card3 art -> map (2500ms)")
b.adb.swipe(759, 430, 640, 400, ms=2500)
img, d = st("after drag")
time.sleep(1.2)
img2, d2 = st("1.2s later")
if d2["attack_v"] == 128 or d["attack_v"] == 128:
    print("   *** PLACEMENT MODE (dim) detected ***")
    # look for the confirm button: bright green blob
    hsv = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    m = ((h > 50) & (h < 85) & (s > 130) & (v > 150)).astype(np.uint8) * 255
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs = sorted([(int(cv2.contourArea(c)), cv2.boundingRect(c)) for c in cnts
                    if cv2.contourArea(c) > 500], reverse=True)[:6]
    print("   green blobs (candidate confirm):", blobs)
    cv2.imwrite("logs/drag2_placement.png", img2)
else:
    print("   no dim -> drag did not start placement")
