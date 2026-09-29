"""Test long-press and drag pickup from the shop card, with region signatures."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def sig(img):
    """Region signatures that differ between village / shop / placement mode."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    out = {}
    out["attack_btn"] = hsv[620, 90].tolist()          # orange in village
    out["shop_btn"] = hsv[655, 1207].tolist()          # gold hammer in village
    out["bl_corner"] = hsv[690, 60].tolist()           # bottom-left corner
    out["br_corner"] = hsv[690, 1220].tolist()         # bottom-right corner
    out["bottom_mid"] = hsv[655, 640].tolist()         # bottom middle
    out["center"] = hsv[400, 640].tolist()             # village center
    return out

def open_shop_to_resources():
    img, gray = b.grab()
    if not b.vis.find(gray, "shop_close", 0.80):
        m = b.vis.find(gray, "shop_button", 0.70)
        if not m:
            print("  !! cannot find shop button"); return None
        b.adb.tap(m[0], m[1], 2); time.sleep(2.0)
    b.adb.tap(316, 65, 3); time.sleep(1.1)
    b.adb.tap(525, 221, 3); time.sleep(1.1)
    img, gray = b.grab()
    if not b.vis.find(gray, "shop_close", 0.80):
        print("  !! shop not open"); return None
    return img

print("=== baseline: plain village signature ===")
v_img, _ = b.grab()
v_sig = sig(v_img)
print("village:", v_sig)

print("=== TEST 1: long-press card3 art (1.5s) ===")
img = open_shop_to_resources()
print("shop sig at card3 area:", sig(img)["center"])
b.adb.swipe(759, 430, 759, 430, ms=1500)
time.sleep(1.2)
img1, gray1 = b.grab(); cv2.imwrite("logs/drag_longpress.png", img1)
print("after long-press:", sig(img1), "shop_open=", bool(b.vis.find(gray1, "shop_close", 0.80)))

print("=== TEST 2: drag card3 art -> village center ===")
img = open_shop_to_resources()
if img is not None:
    b.adb.swipe(759, 430, 640, 380, ms=2000)
    time.sleep(1.2)
    img2, gray2 = b.grab(); cv2.imwrite("logs/drag_drag.png", img2)
    print("after drag:", sig(img2), "shop_open=", bool(b.vis.find(gray2, "shop_close", 0.80)))
