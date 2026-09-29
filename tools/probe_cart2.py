"""Cart model test: does the top-right icon change after adding a card?"""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def open_res():
    img, gray = b.grab()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    if int(hsv[620, 90][2]) == 128:      # stuck in editor -> exit
        b.adb.keyevent(4); time.sleep(1.0)
    if not b.vis.find(gray, "shop_close", 0.80):
        m = b.vis.find(gray, "shop_button", 0.70)
        if not m:
            return None
        b.adb.tap(m[0], m[1], 2); time.sleep(2.0)
    b.adb.tap(316, 65, 3); time.sleep(1.1)
    b.adb.tap(525, 221, 3); time.sleep(1.1)
    img, gray = b.grab()
    if not b.vis.find(gray, "shop_close", 0.80):
        return None
    return img

img1 = open_res()
assert img1 is not None, "shop open failed"
cv2.imwrite("logs/cart2_before.png", img1)
# crop the top-right icon area (the 'C' glyph icon) and the whole top bar right side
before_icon = img1[130:190, 1180:1250].copy()
before_top = img1[0:110, 1000:1280].copy()

# tap card3 art once
b.adb.tap(759, 430, 2)
time.sleep(1.8)
imgA, grayA = b.grab()
print("after tap: shop_open =", bool(b.vis.find(grayA, "shop_close", 0.80)))

# reopen and compare
img2 = open_res()
if img2 is None:
    print("could not reopen shop")
    sys.exit(1)
after_icon = img2[130:190, 1180:1250].copy()
after_top = img2[0:110, 1000:1280].copy()
d_icon = float(np.abs(before_icon.astype(int) - after_icon.astype(int)).mean())
d_top = float(np.abs(before_top.astype(int) - after_top.astype(int)).mean())
print(f"diff icon area = {d_icon:.2f}   diff top bar = {d_top:.2f}")
if d_icon > 6:
    cv2.imwrite("logs/cart2_icon_before.png", before_icon)
    cv2.imwrite("logs/cart2_icon_after.png", after_icon)
    print("icon area changed -> cart/badge state likely modified")
else:
    print("icon area unchanged -> no cart badge change")

# also try tapping the icon itself
b.adb.tap(1211, 157, 2)
time.sleep(1.4)
img3, gray3 = b.grab()
cv2.imwrite("logs/cart2_after_cart_tap.png", img3)
hsv3 = cv2.cvtColor(img3, cv2.COLOR_BGR2HSV)
print("after cart-icon tap: shop=", bool(b.vis.find(gray3, "shop_close", 0.80)),
      "attack_v=", int(hsv3[620, 90][2]),
      "res=", b.vis.read_village_resources(img3))
