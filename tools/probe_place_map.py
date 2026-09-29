"""Tap card -> tap map -> diff: is a building ghost being placed?"""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import Bot, load_config

b = Bot(load_config())
b.adb.ensure_connected()

def open_shop_to_resources():
    img, gray = b.grab()
    if not b.vis.find(gray, "shop_close", 0.80):
        m = b.vis.find(gray, "shop_button", 0.70)
        b.adb.tap(m[0], m[1], 2); time.sleep(2.0)
    b.adb.tap(316, 65, 3); time.sleep(1.1)
    b.adb.tap(525, 221, 3); time.sleep(1.1)
    img, gray = b.grab()
    return bool(b.vis.find(gray, "shop_close", 0.80))

def diff(a, b):
    return float(np.abs(a.astype(int) - b.astype(int)).mean())

print("open shop:", open_shop_to_resources())
before_res = None
b.adb.tap(759, 430, 2)        # tap Gold Mine card art
time.sleep(1.3)
imgA, grayA = b.grab()
before_res = b.vis.read_village_resources(imgA)
cv2.imwrite("logs/pm_A_after_card.png", imgA)
print("A after card tap: shop_open=", bool(b.vis.find(grayA, "shop_close", 0.80)),
      "home=", bool(b.vis.find(grayA, "attack_button", 0.78)), "res=", before_res)

b.adb.tap(640, 420, 2)        # tap the map
time.sleep(1.0)
imgB, grayB = b.grab()
cv2.imwrite("logs/pm_B_after_map.png", imgB)
print("B after map tap  : diff vs A =", round(diff(imgA, imgB), 3),
      "res=", b.vis.read_village_resources(imgB))

b.adb.tap(500, 480, 2)        # tap another map spot
time.sleep(1.0)
imgC, grayC = b.grab()
cv2.imwrite("logs/pm_C.png", imgC)
print("C after map tap2 : diff vs B =", round(diff(imgB, imgC), 3),
      "res=", b.vis.read_village_resources(imgC))
print("bottom-left corner px  :", cv2.cvtColor(imgC, cv2.COLOR_BGR2HSV)[620, 90].tolist())
