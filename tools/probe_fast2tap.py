"""Card tap -> near-immediate map tap (various delays): does placement start?"""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def state():
    img, gray = b.grab()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    m = ((h > 45) & (h < 90) & (s > 110) & (v > 140)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    discs = sorted([(int(cv2.contourArea(c)), cv2.boundingRect(c)) for c in cs
                    if cv2.contourArea(c) > 700], reverse=True)[:3]
    return {"shop": bool(b.vis.find(gray, "shop_close", 0.80)),
            "attack_v": int(v[620, 90]),
            "res": b.vis.read_village_resources(img),
            "green": discs}

def open_res():
    img, gray = b.grab()
    if int(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[620, 90][2]) != 255:
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

for dly, spot in ((0.30, (640, 420)), (0.50, (500, 500)), (0.80, (760, 520))):
    print(f"--- card tap, then map tap at +{dly}s at {spot} ---")
    if not open_res():
        print("   shop open failed"); continue
    b.adb.tap(759, 430, 2)
    time.sleep(dly)
    b.adb.tap(spot[0], spot[1], 2)
    time.sleep(1.0)
    s1 = state()
    time.sleep(1.5)
    s2 = state()
    print("   +1.0s:", s1)
    print("   +2.5s:", s2)
    if s1["attack_v"] in (128, 151) or s2["attack_v"] in (128, 151) or s1["green"] or s2["green"]:
        print("   *** placement-like state detected ***")
        cv2.imwrite(f"logs/fast2tap_{int(dly*100)}.png", b.grab()[0])
        break
