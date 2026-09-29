"""Probe the shop buy flow: open shop -> Resources tab -> tap a card price
button and observe what the client does (placement mode? popup? nothing?).

Read-only with respect to money: it only taps the Gold Mine card (150 elixir)
and cancels/undoes anything that starts, then reports the observed UI.
"""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()
print("state before:", b.current_state())

# 1. open shop
b.adb.tap(1210, 655, 2); time.sleep(2.0)
img, gray = b.grab(); cv2.imwrite("logs/probe_shop_open.png", img)
print("shop header present:", b.vis.find(gray, "close_modal", 0.6) is not None)

# 2. Buildings & Traps tab (hammer) then Resources sub-tab
b.adb.tap(316, 65, 2); time.sleep(1.2)
b.adb.tap(525, 221, 2); time.sleep(1.2)
img, gray = b.grab(); cv2.imwrite("logs/probe_res_tab.png", img)

def signature(img):
    """Classify what's on screen: 'shop' (dark panel), 'village' (grass)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    panel = hsv[300, 900].tolist()      # gray panel area in shop / grass in village
    grass = hsv[500, 200].tolist()
    return {"panel_px": panel, "left_px": grass}

print("A(shop centered):", signature(img))

# 3. tap the Gold Mine card PRICE BUTTON (150 elixir) at its bottom area
for label, (tx, ty) in [("price_button", (759, 588)), ("card_center", (759, 430))]:
    b.adb.tap(tx, ty, 2)
    time.sleep(1.0)
    img1, _ = b.grab(); cv2.imwrite(f"logs/probe_after_{label}_1s.png", img1)
    time.sleep(2.0)
    img2, gray2 = b.grab(); cv2.imwrite(f"logs/probe_after_{label}_3s.png", img2)
    st, reason = b.current_state()
    print(f"tap {label} ({tx},{ty}): state={st.value} ({reason})")
    print("   sig @1s:", signature(img1))
    print("   sig @3s:", signature(img2))
    print("   resources:", b.vis.read_village_resources(img2))
    # if we ended up in a village, ESC back into the shop for the next probe
    if st.value in ("home_village", "unknown"):
        b.adb.tap(1210, 655, 2); time.sleep(1.8)
        b.adb.tap(316, 65, 2); time.sleep(1.0)
        b.adb.tap(525, 221, 2); time.sleep(1.0)
print("done")
