"""Test press-duration variants on a shop card (250/500/800ms presses)."""
import sys, os, time, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def state():
    img, gray = b.grab()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return {"shop": bool(b.vis.find(gray, "shop_close", 0.80)),
            "attack_v": int(hsv[620, 90][2]),
            "res": b.vis.read_village_resources(img)}

def open_res():
    img, gray = b.grab()
    if int(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[620, 90][2]) != 255:
        # not plain village: try to escape dialogs/shop/editor
        for _ in range(3):
            b.adb.keyevent(4); time.sleep(0.8)
            img, gray = b.grab()
            if int(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[620, 90][2]) == 255:
                break
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

for dur in (250, 500, 800):
    for spot, label in (((759, 588), "price"), ((759, 430), "art")):
        print(f"--- press {dur}ms on card3 {label} {spot} ---")
        if not open_res():
            print("   shop open failed"); continue
        print("   before:", state())
        b.adb.swipe(spot[0], spot[1], spot[0], spot[1], dur)
        time.sleep(0.7)
        s1 = state()
        time.sleep(1.0)
        s2 = state()
        print("   +0.7s:", s1)
        print("   +1.7s:", s2)
        if not s2["shop"] and (s2["attack_v"] == 128 or s1["attack_v"] == 128):
            print("   *** PLACEMENT MODE ***")
            sys.exit(0)
