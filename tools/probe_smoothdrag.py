"""Smooth multi-step motionevent drag from a shop card to the map."""
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

if not open_res():
    print("shop open failed"); sys.exit(1)
print("before:", state())

x0, y0 = 759, 430
x1, y1 = 560, 430          # slide out of the card towards the map
print("smooth drag:", (x0, y0), "->", (x1, y1))
b.adb.shell(f"input motionevent DOWN {x0} {y0}")
time.sleep(0.7)
steps = 12
for i in range(1, steps + 1):
    xi = int(x0 + (x1 - x0) * i / steps)
    yi = int(y0 + (y1 - y0) * i / steps)
    b.adb.shell(f"input motionevent MOVE {xi} {yi}")
    time.sleep(0.12)
time.sleep(0.5)
b.adb.shell(f"input motionevent UP {x1} {y1}")
time.sleep(0.6)
print("+0.6s:", state())
time.sleep(1.5)
print("+2.1s:", state())
img, gray = b.grab()
cv2.imwrite("logs/smooth_drag_result.png", img)
if int(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[620, 90][2]) == 128:
    print("*** PLACEMENT MODE ***")
