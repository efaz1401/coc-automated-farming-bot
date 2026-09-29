"""Calibrate: screenshot via ADB, click to print fractional coords, capture templates.
Usage: python tools/calibrate.py
Keys: q=quit, r=refresh screenshot, s=save full screenshot,
      l=loot box (click top-left then bottom-right of the GOLD number;
      prints ready-to-paste vision.loot_boxes YAML with elixir/dark offsets).
"""
import cv2
import numpy as np
import subprocess
import os
import datetime

W, H = 1280, 720
os.makedirs("assets", exist_ok=True)

def shot():
    r = subprocess.run(["adb", "exec-out", "screencap", "-p"], capture_output=True, timeout=20)
    img = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)
    return cv2.resize(img, (W, H))

img = shot()
print("Click image to print fractional coords. Keys: r=refresh, s=screenshot, "
      "l=loot box (2 clicks), q=quit")
loot_mode = False
loot_clicks = []

def on_mouse(ev, x, y, flags, param):
    global loot_mode, loot_clicks
    if ev != cv2.EVENT_LBUTTONDOWN:
        return
    if loot_mode:
        loot_clicks.append((x, y))
        if len(loot_clicks) == 1:
            print("top-left set — now click BOTTOM-RIGHT of the number")
        else:
            (x1, y1), (x2, y2) = loot_clicks
            bx, by = min(x1, x2) / W, min(y1, y2) / H
            bw, bh = abs(x2 - x1) / W, abs(y2 - y1) / H
            print("# paste under vision: in config.yaml")
            print("  loot_boxes:")
            print(f"    gold:   [{bx:.3f}, {by:.3f}, {bw:.3f}, {bh:.3f}]")
            print(f"    elixir: [{bx:.3f}, {by + 0.07:.3f}, {bw:.3f}, {bh:.3f}]")
            print(f"    dark:   [{bx:.3f}, {by + 0.14:.3f}, {bw:.3f}, {bh:.3f}]")
            loot_mode, loot_clicks = False, []
            cv2.imshow("calibrate", img)
        return
    print(f"frac: [{x/W:.3f}, {y/H:.3f}]  px: ({x},{y})")
    tmp = img.copy()
    cv2.circle(tmp, (x, y), 8, (0, 0, 255), 2)
    cv2.imshow("calibrate", tmp)

cv2.imshow("calibrate", img)
cv2.setMouseCallback("calibrate", on_mouse)
while True:
    k = cv2.waitKey(50) & 0xFF
    if k == ord("q"):
        break
    if k == ord("r"):
        img = shot()
        cv2.imshow("calibrate", img)
    if k == ord("s"):
        os.makedirs("logs", exist_ok=True)
        fn = f"logs/cal_{datetime.datetime.now():%H%M%S}.png"
        cv2.imwrite(fn, img)
        print("saved", fn)
    if k == ord("l"):
        loot_mode = True
        loot_clicks = []
        print("loot box: click TOP-LEFT of the gold number, then BOTTOM-RIGHT")
cv2.destroyAllWindows()
