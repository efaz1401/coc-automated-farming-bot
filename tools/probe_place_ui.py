"""Enter placement mode via the map badge, map out the confirm/cancel UI,
save templates, then cancel safely with BACK."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

# plain-village reference frame (bright, no editor)
img0, gray0 = b.grab()
cv2.imwrite("logs/pui_village.png", img0)

print("tapping Rebuild badge (199,661) to enter placement mode (CC)...")
b.adb.tap(199, 661, 2)
time.sleep(1.4)
img1, gray1 = b.grab()
cv2.imwrite("logs/pui_mode1.png", img1)
hsv1 = cv2.cvtColor(img1, cv2.COLOR_BGR2HSV)
print("attack_v:", int(hsv1[620, 90][2]), "(128 = placement/editor)")

# diff vs village to find NEW UI elements
d = np.abs(img0.astype(int) - img1.astype(int)).max(axis=2)
m = (d > 45).astype(np.uint8) * 255
m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
blobs = sorted([(int(cv2.contourArea(c)), cv2.boundingRect(c)) for c in cnts
                if cv2.contourArea(c) > 400], reverse=True)
print("new/changed UI regions (area, x,y,w,h):")
for a, r in blobs[:10]:
    print("   ", a, r)

# candidate buttons: coloured discs anywhere in the lower half
h, s, v = hsv1[:, :, 0], hsv1[:, :, 1], hsv1[:, :, 2]
for name, mask in {"green": (h > 45) & (h < 90) & (s > 110) & (v > 140),
                   "red": (((h < 10) | (h > 168)) & (s > 150) & (v > 140))}.items():
    mm = mask.astype(np.uint8) * 255
    mm = cv2.morphologyEx(mm, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cs, _ = cv2.findContours(mm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bb = sorted([(int(cv2.contourArea(c)), cv2.boundingRect(c)) for c in cs
                 if cv2.contourArea(c) > 500 and cv2.boundingRect(c)[1] > 400],
                reverse=True)[:6]
    print(f"{name} discs (lower half):", bb)
    for a, (x, y, w, hh) in bb[:2]:
        pad = 10
        crop = img1[max(0, y - pad):y + hh + pad, max(0, x - pad):x + w + pad]
        fn = f"logs/cand_{name}_{x}_{y}.png"
        cv2.imwrite(fn, crop)
        print("   saved", fn, crop.shape)

print("cancelling with BACK...")
b.adb.keyevent(4)
time.sleep(1.2)
img2, gray2 = b.grab()
print("attack_v after BACK:", int(cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)[620, 90][2]),
      "| home:", bool(b.vis.find(gray2, "attack_button", 0.78)))
