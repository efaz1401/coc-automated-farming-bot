"""Probe the shop cart flow: add a building to the cart, then check out."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def frame():
    img, gray = b.grab()
    shop = b.vis.find(gray, "shop_close", 0.80)
    home = b.vis.find(gray, "attack_button", 0.78)
    cart = b.vis.find(gray, "cart_button", 0.70) if "cart_button" in b.vis.templates else None
    return img, gray, shop, home, cart

img, gray, shop, home, cart = frame()
print(f"start: shop={bool(shop)} home={bool(home)}")
if not shop:
    m = b.vis.find(gray, "shop_button", 0.70)
    print("opening shop via", m)
    b.adb.tap(m[0], m[1], 2); time.sleep(2.2)
    img, gray, shop, home, cart = frame()
    print("  shop now:", bool(shop))

# capture the cart icon template from this live frame (top-right of shop)
cv2.imwrite("assets/cart_button.png", img[130:185, 1180:1245])

# go to Buildings & Traps -> Resources
b.adb.tap(316, 65, 3); time.sleep(1.2)
b.adb.tap(525, 221, 3); time.sleep(1.2)
img, gray, shop, home, cart = frame()
print("on Resources tab:", bool(shop))

# STEP 1: tap the Gold Mine card ART (3rd card) and observe in fine detail
for step, (tx, ty, label) in enumerate([
        (759, 430, "card3_art"), (759, 588, "card3_price"),
        (759, 430, "card3_art_again")], start=1):
    before = b.vis.read_village_resources(b.grab()[0])
    b.adb.tap(tx, ty, 2)
    time.sleep(1.0)
    img, gray, shop, home, cart = frame()
    after = b.vis.read_village_resources(img)
    cv2.imwrite(f"logs/cart_step{step}_{label}.png", img)
    print(f"step{step} tap {label}: shop_open={bool(shop)} home={bool(home)} "
          f"res_before={before} res_after={after}")
    if not shop:
        break

# STEP 2: if the shop is still open, try the cart/checkout icon
img, gray, shop, home, cart = frame()
if shop:
    print("tapping cart icon (1211, 157)")
    b.adb.tap(1211, 157, 2)
    time.sleep(1.5)
    img, gray, shop, home, cart = frame()
    cv2.imwrite("logs/cart_checkout.png", img)
    print(f"after cart tap: shop_open={bool(shop)} home={bool(home)}")
    print("resources:", b.vis.read_village_resources(img))
