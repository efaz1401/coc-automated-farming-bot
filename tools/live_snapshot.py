"""Report exactly what is on screen right now (templates + state)."""
import sys, os, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()
img, gray = b.grab()
cv2.imwrite("logs/live_now.png", img)
print("state:", b.current_state())
print("PIXELS  (640,30):", cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[30, 640].tolist(),
      " (900,300):", cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[300, 900].tolist(),
      " (200,500):", cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[500, 200].tolist())
for name in ("attack_button", "builder_face", "shop_button", "shop_close",
             "reload_button", "reload_dialog", "close_modal", "suggested_upgrades",
             "all_builders_busy", "finish_now", "upgrade_button", "train_button"):
    if name in b.vis.templates:
        m = b.vis.find(gray, name, 0.70)
        print(f"  {name:22s} -> {m}")
    else:
        print(f"  {name:22s} -> (template missing)")
print("resources:", b.vis.read_village_resources(img))
print("storage  :", b.vis.read_storage_fill(img))
