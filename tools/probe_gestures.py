"""Try multiple gesture primitives on a shop card and observe which (if any)
starts the placement flow."""
import sys, os, time, cv2, numpy as np
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

def open_res(verify=True):
    img, gray = b.grab()
    if int(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[620, 90][2]) == 128:
        b.adb.keyevent(4); time.sleep(1.0)
        img, gray = b.grab()
    if not b.vis.find(gray, "shop_close", 0.80):
        m = b.vis.find(gray, "shop_button", 0.70)
        if not m:
            print("   no shop button"); return False
        b.adb.tap(m[0], m[1], 2); time.sleep(2.0)
    b.adb.tap(316, 65, 3); time.sleep(1.1)
    b.adb.tap(525, 221, 3); time.sleep(1.1)
    img, gray = b.grab()
    ok = bool(b.vis.find(gray, "shop_close", 0.80))
    lm = b.vis.find_near(gray, "price_gold", 476, 596, 28, 0.70)
    if verify:
        print(f"   shop={ok} resources_tab_landmark={lm}")
    return ok and bool(lm)

print("native 'input' capabilities:")
print(b.adb.shell("input 2>&1 | head -20"))

tests = [
    ("draganddrop 900ms", lambda: b.adb.shell("input draganddrop 759 430 500 450 900")),
    ("draganddrop 1500ms", lambda: b.adb.shell("input draganddrop 759 430 500 450 1500")),
    ("motionevent seq", lambda: [
        b.adb.shell("input motionevent DOWN 759 430"),
        time.sleep(0.9),
        b.adb.shell("input motionevent MOVE 640 420"),
        time.sleep(0.4),
        b.adb.shell("input motionevent UP 640 420"),
    ]),
    ("swipe 600ms", lambda: b.adb.swipe(759, 430, 500, 450, 600)),
]

for name, act in tests:
    print(f"--- {name} ---")
    if not open_res():
        print("   reopen failed, skipping")
        continue
    print("   before:", state())
    act()
    time.sleep(0.5)
    s1 = state()
    time.sleep(1.2)
    s2 = state()
    print("   +0.5s:", s1)
    print("   +1.7s:", s2)
    if s2["attack_v"] == 128 or s1["attack_v"] == 128:
        print("   *** PLACEMENT MODE DETECTED ***")
        cv2.imwrite(f"logs/gest_{name.split()[0]}_placement.png", b.grab()[0])
        b.adb.keyevent(4); time.sleep(0.8)
        break
