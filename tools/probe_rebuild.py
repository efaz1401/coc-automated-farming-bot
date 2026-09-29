"""Probe the map's 'Rebuild' marker flow (Clan Castle) — observe only."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

img, gray = b.grab()
print("before:", b.current_state(), b.vis.read_village_resources(img))
cv2.imwrite("logs/rb_before.png", img)

# locate the 'Rebuild' label: white text on dark rounded box near (166-240, 610-645)
# use the red '!' badge next to it: red blob in region x 150-260, y 600-700
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
reg = hsv[590:700, 140:280]
h, s, v = reg[:, :, 0], reg[:, :, 1], reg[:, :, 2]
red = (((h < 10) | (h > 170)) & (s > 150) & (v > 150)).astype(np.uint8) * 255
cnts, _ = cv2.findContours(red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
blobs = sorted([(int(cv2.contourArea(c)), cv2.boundingRect(c)) for c in cnts
                if cv2.contourArea(c) > 150], reverse=True)
print("red badge blobs near Rebuild:", blobs)

# tap the label box (above/left of the badge)
for tx, ty, what in [(202, 626, "label"), (199, 661, "badge")]:
    print(f"--- tapping {what} at ({tx},{ty}) ---")
    b.adb.tap(tx, ty, 2)
    time.sleep(1.6)
    img2, gray2 = b.grab()
    cv2.imwrite(f"logs/rb_after_{what}.png", img2)
    hsv2 = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)
    print("   attack_v:", int(hsv2[620, 90][2]),
          "| home:", bool(b.vis.find(gray2, "attack_button", 0.78)),
          "| shop:", bool(b.vis.find(gray2, "shop_close", 0.80)))
    # dialog landmarks: any of our confirm templates / upgrade button / gem
    for key in ("upgrade_button", "confirm_upgrade_gold", "confirm_upgrade_elixir",
                "finish_now", "gem_icon", "all_builders_busy"):
        m = b.vis.find(gray2, key, 0.70)
        if m:
            print(f"   {key}: {m}")
    print("   res:", b.vis.read_village_resources(img2))
    # if a build/move mode started, cancel it
    if int(hsv2[620, 90][2]) == 128 or b.vis.find(gray2, "finish_now", 0.7):
        print("   -> placement/editor mode; pressing BACK to cancel")
        b.adb.keyevent(4); time.sleep(1.0)
        img3, gray3 = b.grab()
        print("   after BACK attack_v:",
              int(cv2.cvtColor(img3, cv2.COLOR_BGR2HSV)[620, 90][2]))
