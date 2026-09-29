"""Single-invocation motionevent gesture: DOWN, hold (dup MOVEs), drag, UP."""
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

# single command: hold at the card, then drag to the map, then release
hold = " ".join(f"MOVE 759 430" for _ in range(20))       # ~1s hold
path = " ".join(f"MOVE {759 - i * 20} {430 + i * 2}" for i in range(1, 11))
cmd = f"input motionevent DOWN 759 430 {hold} {path} UP 559 450"
out = b.adb.shell(cmd)
print("cmd out:", repr(out)[:200])
time.sleep(0.8)
print("+0.8s:", state())
time.sleep(1.5)
print("+2.3s:", state())
img, gray = b.grab()
cv2.imwrite("logs/onecmd_drag.png", img)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
if int(hsv[620, 90][2]) == 128:
    print("*** PLACEMENT MODE ENTERED ***")
    # find bright green confirm disc
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    m = ((h > 45) & (h < 90) & (s > 110) & (v > 140)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    discs = sorted([(int(cv2.contourArea(c)), cv2.boundingRect(c)) for c in cs
                    if cv2.contourArea(c) > 800], reverse=True)[:5]
    print("green discs:", discs)
    for a, (x, y, w, hh) in discs[:3]:
        # check for white checkmark inside (button signature)
        crop = img[y:y + hh, x:x + w]
        if crop.size:
            g2 = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            white = float((g2 > 200).mean())
            print(f"   disc at ({x},{y},{w},{hh}) white_frac={white:.2f}")
            cv2.imwrite(f"logs/disc_{x}_{y}.png", crop)
