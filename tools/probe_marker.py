"""Probe: red '!' build-site markers on the village map (Rebuild/New labels)."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def red_badge_blobs(img):
    """Find red circular '!' badges on the map (exclude known HUD spots)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    mask = ((((h < 10) | (h > 170)) & (s > 150) & (v > 150))).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        a = cv2.contourArea(c)
        if a < 250:
            continue
        x, y, w, hh = cv2.boundingRect(c)
        # skip known HUD badges: shop icon (x>1150,y 560-620), battle log (1050-1130, 600-660)
        if x > 1150 and 560 < y < 630:
            continue
        if 1050 < x < 1130 and 600 < y < 660:
            continue
        out.append((int(a), x, y, w, hh))
    return sorted(out, reverse=True)

def frame():
    return b.grab()

img, gray = frame()
cv2.imwrite("logs/mk_before.png", img)
blobs = red_badge_blobs(img)
print("red badge candidates:", blobs)

# tap the biggest marker's label (label sits to the right/above the badge)
if blobs:
    a, x, y, w, h = blobs[0]
    cx, cy = x + w // 2, y + h // 2
    print(f"tapping marker badge center ({cx},{cy}) area={a}")
    b.adb.tap(cx, cy, 2)
    time.sleep(1.6)
    img2, gray2 = frame()
    cv2.imwrite("logs/mk_after_badge_tap.png", img2)
    dim = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)[620, 90].tolist()
    print("after badge tap: attack_btn px =", dim, "(v~128 => placement/move mode)")
    print("  shop open:", bool(b.vis.find(gray2, "shop_close", 0.80)))
    print("  upgrade_button:", b.vis.find(gray2, "upgrade_button", 0.70))
    print("  confirm_upgrade_gold:", b.vis.find(gray2, "confirm_upgrade_gold", 0.70))
    print("  resources:", b.vis.read_village_resources(img2))

    # if a place/move mode started, cancel with BACK
    b.adb.keyevent(4)
    time.sleep(1.0)
    img3, gray3 = frame()
    print("after BACK: attack_btn px =", cv2.cvtColor(img3, cv2.COLOR_BGR2HSV)[620, 90].tolist())
