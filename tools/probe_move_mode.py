"""Learn what CoC placement/move mode looks like: long-press a building,
capture the UI, then CANCEL with the Android BACK key (never confirms)."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def regions(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return {
        "attack_btn": hsv[620, 90].tolist(),
        "shop_btn": hsv[655, 1207].tolist(),
        "bl": hsv[690, 60].tolist(),
        "br": hsv[690, 1220].tolist(),
        "bm": hsv[655, 640].tolist(),
    }

img0, gray0 = b.grab()
cv2.imwrite("logs/mv_before.png", img0)
print("BEFORE :", regions(img0))
print("home:", bool(b.vis.find(gray0, "attack_button", 0.78)))

# make sure we are on the plain village: press BACK once (safe in village)
b.adb.keyevent(4); time.sleep(1.0)
img0b, gray0b = b.grab()
print("after BACK:", bool(b.vis.find(gray0b, "attack_button", 0.78)))

# long-press the elixir collector to pick it up (move mode)
BXI, BYI = 365, 425
b.adb.swipe(BXI, BYI, BXI, BYI, ms=1200)
time.sleep(1.2)
img1, gray1 = b.grab()
cv2.imwrite("logs/mv_picked.png", img1)
print("PICKED :", regions(img1))
print("home still?", bool(b.vis.find(gray1, "attack_button", 0.78)))

# find green/red circular buttons anywhere in the frame (placement UI)
hsv1 = cv2.cvtColor(img1, cv2.COLOR_BGR2HSV)
h, s, v = hsv1[:, :, 0], hsv1[:, :, 1], hsv1[:, :, 2]
for name, mask in {
    "green": ((h > 50) & (h < 85) & (s > 130) & (v > 150)),
    "red": (((h < 8) | (h > 170)) & (s > 170) & (v > 150)),
}.items():
    m = (mask.astype(np.uint8)) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs = sorted([(int(cv2.contourArea(c)), cv2.boundingRect(c)) for c in cnts
                    if cv2.contourArea(c) > 600], reverse=True)[:5]
    print(f"  {name} blobs:", blobs)

# CANCEL the move with BACK (never confirm)
b.adb.keyevent(4); time.sleep(1.2)
img2, gray2 = b.grab()
cv2.imwrite("logs/mv_cancelled.png", img2)
print("CANCELLED:", regions(img2))
print("home:", bool(b.vis.find(gray2, "attack_button", 0.78)))
d = float(np.abs(img0.astype(int) - img2.astype(int)).mean())
print("diff before-vs-cancelled:", round(d, 3))
