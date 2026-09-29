"""Probe: is the current screen a plain village or building-placement mode?

Placement mode shows a green confirm (✓) and red cancel (✗) circular button.
Plain village shows the Attack!/Shop buttons instead.
"""
import sys, os, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def green_mask(img, x0, y0, x1, y1):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[y0:y1, x0:x1]
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    return ((h > 50) & (h < 75) & (s > 120) & (v > 120))

def red_mask(img, x0, y0, x1, y1):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[y0:y1, x0:x1]
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    return (((h < 8) | (h > 172)) & (s > 150) & (v > 140))

def blobs(mask):
    m = (mask * 255).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        a = cv2.contourArea(c)
        if a > 400:
            x, y, w, h = cv2.boundingRect(c)
            out.append((int(a), (x, y, w, h)))
    return sorted(out, reverse=True)

for path in ("logs/analysis_now.png", "logs/after_card_tap.png"):
    img = cv2.imread(path)
    if img is None:
        print(path, "MISSING"); continue
    g = green_mask(img, 0, 560, 1280, 720)
    r = red_mask(img, 0, 560, 1280, 720)
    print("=" * 50)
    print(os.path.basename(path))
    print("  green blobs (bottom strip):", blobs(g)[:4])
    print("  red   blobs (bottom strip):", blobs(r)[:4])
    # save candidate template if a green button blob exists
    gb = blobs(g)
    if gb:
        a, (x, y, w, h) = gb[0]
        pad = 12
        crop = img[max(0, 560 + y - pad):560 + y + h + pad, max(0, x - pad):x + w + pad]
        name = "logs/place_confirm_candidate.png"
        cv2.imwrite(name, crop)
        print("  -> saved", name, crop.shape)
    rb = blobs(r)
    if rb:
        a, (x, y, w, h) = rb[0]
        pad = 12
        crop = img[max(0, 560 + y - pad):560 + y + h + pad, max(0, x - pad):x + w + pad]
        cv2.imwrite("logs/place_cancel_candidate.png", crop)
        print("  -> saved logs/place_cancel_candidate.png", crop.shape)
