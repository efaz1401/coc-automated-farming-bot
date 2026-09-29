"""Try different input sources (mouse/touchpad/touchscreen) on a shop card."""
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
    if int(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[620, 90][2]) == 128:
        b.adb.keyevent(4); time.sleep(1.0)
        img, gray = b.grab()
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

for src in ("mouse", "touchpad", "touchscreen", "stylus"):
    print(f"--- source={src}: tap card3 art ---")
    if not open_res():
        print("   could not open shop"); continue
    print("   before:", state())
    out = b.adb.shell(f"input {src} tap 759 430")
    print("   cmd out:", repr(out))
    time.sleep(0.6)
    s1 = state()
    time.sleep(1.2)
    s2 = state()
    print("   +0.6s:", s1)
    print("   +1.8s:", s2)
    if s1["attack_v"] == 128 or s2["attack_v"] == 128:
        print("   *** PLACEMENT MODE ***")
        cv2.imwrite(f"logs/src_{src}_placement.png", b.grab()[0])
        break
    if not s2["shop"] and s2["res"]["gold"] not in (-1, 2716):
        print("   *** PURCHASE HAPPENED? res changed ***")
        break
