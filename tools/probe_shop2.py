"""Deterministic shop probe using template-verified landmarks only."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

# --- capture landmark templates once (from saved live screenshots) ---
village = cv2.imread("logs/after_card_tap.png")
shop = cv2.imread("logs/shop_res.png")

# shop button in bottom-right of village
cv2.imwrite("assets/shop_button.png", village[600:712, 1140:1275])

# shop red X close button: find its bbox precisely
hsv = cv2.cvtColor(shop, cv2.COLOR_BGR2HSV)
reg = hsv[20:95, 1185:1265]
h, s, v = reg[:, :, 0], reg[:, :, 1], reg[:, :, 2]
red = (((h < 8) | (h > 170)) & (s > 150) & (v > 150)).astype(np.uint8)
ys, xs = np.nonzero(red)
if len(xs):
    x0, x1 = xs.min() + 1185, xs.max() + 1185
    y0, y1 = ys.min() + 20, ys.max() + 20
    print("X-button bbox:", x0, y0, x1, y1)
    cv2.imwrite("assets/shop_close.png", shop[y0:y1 + 1, x0:x1 + 1])
    print("saved assets/shop_close.png", (x1 - x0 + 1, y1 - y0 + 1))

b = Bot(load_config())
b.adb.ensure_connected()
print("templates:", [k for k in ("shop_button", "shop_close") if k in b.vis.templates])

def find_shop_close(img, gray):
    m = b.vis.find(gray, "shop_close", 0.70)
    return m

def find_shop_button(img, gray):
    return b.vis.find(gray, "shop_button", 0.70)

# 1. verify home
print("state:", b.current_state())
img, gray = b.grab()
m = find_shop_button(img, gray)
print("shop_button match:", m)
if not m:
    print("ABORT: shop button not found")
    sys.exit(1)

# 2. open shop, verify
b.adb.tap(m[0], m[1], 2); time.sleep(2.0)
img, gray = b.grab()
print("after shop tap -> shop_close match:", find_shop_close(img, gray))
cv2.imwrite("logs/p2_open.png", img)

# 3. Buildings&Traps tab -> Resources sub-tab, verify we're on Resources
b.adb.tap(316, 65, 2); time.sleep(1.2)
b.adb.tap(525, 221, 2); time.sleep(1.2)
img, gray = b.grab()
cv2.imwrite("logs/p2_res.png", img)
print("still in shop:", find_shop_close(img, gray))
# Resources tab landmark: gold-coin price icon of Elixir Collector card (2nd card)
pm = b.vis.find_near(gray, "price_gold", 476, 596, radius=25, thresh=0.70)
print("Elixir Collector gold price icon:", pm)

# 4. tap the Gold Mine price button (3rd card, costs elixir) and observe
res_before = b.vis.read_village_resources(img)
b.adb.tap(759, 588, 2)
for i in range(6):
    time.sleep(0.6)
    img2, gray2 = b.grab()
    close = find_shop_close(img2, gray2)
    st, reason = b.current_state()
    # placement-mode landmarks: new green/red circular button in bottom strip
    hsv2 = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)
    bot_strip = hsv2[590:720]
    hh, ss, vv = bot_strip[:, :, 0], bot_strip[:, :, 1], bot_strip[:, :, 2]
    green = ((hh > 50) & (hh < 80) & (ss > 130) & (vv > 150)).astype(np.uint8) * 255
    green = cv2.morphologyEx(green, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cnts, _ = cv2.findContours(green, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    gblobs = [(int(cv2.contourArea(c)), cv2.boundingRect(c)) for c in cnts if cv2.contourArea(c) > 900]
    print(f"  t+{0.6*(i+1):.1f}s close={bool(close)} state={st.value} green_blobs={gblobs}")
    if i == 5:
        cv2.imwrite("logs/p2_after_tap.png", img2)
print("resources before tap:", res_before)
print("resources now       :", b.vis.read_village_resources(b.grab()[0]))
