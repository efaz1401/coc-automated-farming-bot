"""Is there a placement ghost? Track the gold-colored region and resources."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def gold_region(img):
    """Find the largest bright-gold blob (hue 20-35, sat>180, val>200)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    m = ((h > 18) & (h < 35) & (s > 180) & (v > 200)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs = sorted([(int(cv2.contourArea(c)), cv2.boundingRect(c)) for c in cnts
                    if cv2.contourArea(c) > 300], reverse=True)
    return blobs[:4]

def info(tag):
    img, gray = b.grab()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    d = {"attack_v": int(hsv[620, 90][2]),
         "shop": bool(b.vis.find(gray, "shop_close", 0.80)),
         "home": bool(b.vis.find(gray, "attack_button", 0.78)),
         "res": b.vis.read_village_resources(img),
         "gold_blobs": gold_region(img)}
    print(f"[{tag}] attack_v={d['attack_v']} home={d['home']} res={d['res']}")
    for a, r in d["gold_blobs"]:
        print(f"     gold blob area={a} rect={r}")
    return img, d

img, d = info("now")
cv2.imwrite("logs/ghost_now.png", img)

# tap the map at a different spot and see if a gold blob moves there
print("tapping map at (500,480)")
b.adb.tap(500, 480, 2)
time.sleep(1.2)
img2, d2 = info("after map tap")
cv2.imwrite("logs/ghost_after_tap.png", img2)

# try tapping the map at (900,500)
print("tapping map at (900,500)")
b.adb.tap(900, 500, 2)
time.sleep(1.2)
img3, d3 = info("after 2nd tap")
cv2.imwrite("logs/ghost_after_tap2.png", img3)
