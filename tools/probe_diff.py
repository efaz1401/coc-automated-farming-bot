"""Diff the village BEFORE the shop vs AFTER a card tap: any new UI/ghost?"""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def village_frame():
    img, gray = b.grab()
    return img

# make sure plain village
img, gray = b.grab()
if int(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[620, 90][2]) == 128:
    b.adb.keyevent(4); time.sleep(1.0)
    img, gray = b.grab()
    if not b.vis.find(gray, "attack_button", 0.78):
        print("not at home, aborting"); sys.exit(1)

# move camera slightly and back to reset any selection, then settle
time.sleep(1.0)
before = village_frame()
cv2.imwrite("logs/diff_before.png", before)

# open shop -> resources (verified)
m = b.vis.find(cv2.cvtColor(before, cv2.COLOR_BGR2GRAY), "shop_button", 0.70)
b.adb.tap(m[0], m[1], 2); time.sleep(2.0)
b.adb.tap(316, 65, 3); time.sleep(1.1)
b.adb.tap(525, 221, 3); time.sleep(1.1)
img, gray = b.grab()
assert b.vis.find(gray, "shop_close", 0.80), "shop not open"
assert b.vis.find_near(gray, "price_gold", 476, 596, 28, 0.70), "not on Resources tab"

# tap card3 art
b.adb.tap(759, 430, 2)
time.sleep(2.0)
after = village_frame()
cv2.imwrite("logs/diff_after.png", after)

d = np.abs(before.astype(int) - after.astype(int)).max(axis=2)
print("mean diff:", round(float(d.mean()), 3), "| pixels >40:", int((d > 40).sum()))
# where are the changed pixels?
ys, xs = np.nonzero(d > 40)
if len(xs):
    print("changed region bbox: x", xs.min(), "-", xs.max(), " y", ys.min(), "-", ys.max())
    # cluster rows to see if it's the bottom UI
    import collections
    rows = collections.Counter((ys // 60) * 60)
    print("changed rows histogram (y_bucket: count):", dict(sorted(rows.items())))
    cols = collections.Counter((xs // 120) * 120)
    print("changed cols histogram (x_bucket: count):", dict(sorted(cols.items())))
    # save a heat mask
    hm = np.zeros_like(d, np.uint8); hm[d > 40] = 255
    cv2.imwrite("logs/diff_mask.png", hm)
else:
    print("no significant change -> plain village confirmed (no ghost, no buttons)")
