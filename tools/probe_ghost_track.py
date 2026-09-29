"""Track the post-card-tap state over time; if a placement ghost appears,
place the building for real (Gold Mine = 150 elixir) and verify."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

HUD_GOLD = [(1135, 590, 125, 107), (23, 576, 122, 31), (1137, 17, 126, 48), (25, 285, 57, 46)]

def snap(tag):
    img, gray = b.grab()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    m = ((h > 18) & (h < 35) & (s > 180) & (v > 200)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs = []
    for c in cs:
        a = int(cv2.contourArea(c))
        if a < 400:
            continue
        x, y, w, hh = cv2.boundingRect(c)
        if any(abs(x - hx) < 40 and abs(y - hy) < 40 for hx, hy, hw, hhh in HUD_GOLD):
            continue
        blobs.append((a, (x, y, w, hh)))
    d = {"shop": bool(b.vis.find(gray, "shop_close", 0.80)),
         "attack_v": int(v[620, 90]),
         "nonhud_gold": sorted(blobs, reverse=True)[:3],
         "res": b.vis.read_village_resources(img)}
    print(f"[{tag}] shop={d['shop']} attack_v={d['attack_v']} res={d['res']} gold={d['nonhud_gold']}")
    return img, d

def open_res():
    img, gray = b.grab()
    if int(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[620, 90][2]) == 128:
        b.adb.keyevent(4); time.sleep(1.0); img, gray = b.grab()
    if not b.vis.find(gray, "shop_close", 0.80):
        m = b.vis.find(gray, "shop_button", 0.70)
        if not m:
            return False
        b.adb.tap(m[0], m[1], 2); time.sleep(2.0)
    b.adb.tap(316, 65, 3); time.sleep(1.1)
    b.adb.tap(525, 221, 3); time.sleep(1.1)
    img, gray = b.grab()
    return bool(b.vis.find(gray, "shop_close", 0.80)) and \
        bool(b.vis.find_near(gray, "price_gold", 476, 596, 28, 0.70))

img0, d0 = snap("village-before")
if not open_res():
    print("shop failed"); sys.exit(1)
snap("shop-open")
print(">>> tapping card3 art (Gold Mine)")
b.adb.tap(759, 430, 2)
for t in (0.4, 1.0, 2.0, 4.0, 7.0):
    time.sleep(t if t == 0.4 else 0.6 if t == 1.0 else 1.0 if t == 2.0 else 2.0 if t == 4.0 else 3.0)
    img, d = snap(f"t+{t}")
    if not d["shop"] and d["nonhud_gold"] and not d["res"].get("gold", -1) == 2716:
        pass
# if not in placement, still try tapping where the ghost likely is and look for confirm
imgN, dN = snap("final")
if dN["nonhud_gold"]:
    a, (x, y, w, hh) = dN["nonhud_gold"][0]
    print(f">>> ghost candidate at {(x,y,w,hh)} -> tapping its position")
    b.adb.tap(x + w // 2, y + hh // 2, 2)
    time.sleep(1.0)
    snap("after ghost tap")
