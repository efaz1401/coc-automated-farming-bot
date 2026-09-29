"""Verify a programmatic shop-open detector against saved screenshots."""
import cv2, numpy as np

def shop_signature(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    x_btn = hsv[55, 1219].astype(int)     # red X close button in shop
    top_strip = hsv[30, 640].astype(int)  # dark shop strip / village sky
    red_x = (x_btn[0] < 10 or x_btn[0] > 170) and x_btn[1] > 130 and x_btn[2] > 140
    dark_top = top_strip[2] < 90
    return red_x, dark_top, x_btn.tolist(), top_strip.tolist()

for path in ("logs/shop_1.png", "logs/shop_2.png", "logs/shop_res.png", "logs/shop_def.png",
             "logs/shop_army.png", "logs/analysis_now.png", "logs/after_card_tap.png"):
    img = cv2.imread(path)
    if img is None:
        print(path, "MISSING"); continue
    rx, dt, px, tp = shop_signature(img)
    print(f"{path:35s} red_x={rx} dark_top={dt}  px(1219,55)={px} top(640,30)={tp}  -> shop_open={rx and dt}")
