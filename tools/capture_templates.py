"""Template capture assistant — walk-through drag-crop tool.

Usage:  C:\\Python312\\python.exe tools\\capture_templates.py

For each target (button/digit) it shows your live emulator screenshot;
you drag a rectangle around it and press ENTER to save the correctly-named
file into assets/. Keys inside the ROI selector: ENTER/SPACE=save, c=cancel.
Keys in the main loop: r=refresh screenshot, s=skip target, q=quit.
At the end it prints ready-to-paste vision.loot_boxes YAML (gold drag box).
"""
import os
import sys
import subprocess

import cv2
import numpy as np

W, H = 1280, 720
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
os.makedirs("assets", exist_ok=True)
os.makedirs(os.path.join("assets", "digits"), exist_ok=True)

BUTTONS = [
    ("attack_button",     "your VILLAGE screen — the orange 'Attack' button (bottom-left)"),
    ("find_match",        "attack menu — the 'Find a Match' button"),
    ("next_button",       "scouting view (after Find a Match) — 'Next' button (bottom-right)"),
    ("surrender",         "DURING a battle — the white-flag 'Surrender' button (bottom-left)"),
    ("confirm_surrender", "the 'Okay' confirmation popup after pressing Surrender"),
    ("return_home",       "battle-end screen — the 'Return Home' button"),
    ("train_button",      "village screen — 'Train' troops button (bottom-right)"),
    ("quick_train",       "army/training screen — the 'Quick Train' button"),
]

ADB = "adb"


def grab() -> np.ndarray:
    r = subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True, timeout=20)
    img = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("screencap failed — is the emulator running? (adb devices)")
    return cv2.resize(img, (W, H))


def overview(img, title, sub=""):
    disp = img.copy()
    cv2.rectangle(disp, (0, 0), (W, 60), (0, 0, 0), -1)
    cv2.putText(disp, title, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.putText(disp, sub or "r=refresh  s=skip  q=quit", (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    return disp


def crop_and_save(img, path, label) -> bool:
    x, y, w, h = cv2.selectROI(f"drag around: {label} (ENTER=save, c=cancel)", img, False)
    cv2.destroyWindow(f"drag around: {label} (ENTER=save, c=cancel)")
    if w == 0 or h == 0:
        print("  cancelled")
        return False
    crop = img[int(y):int(y + h), int(x):int(x + w)]
    cv2.imwrite(path, crop)
    print(f"  saved -> {path}  ({w:.0f}x{h:.0f}px)")
    return True


def main():
    img = grab()
    print(f"connected. template root: {os.path.join(ROOT, 'assets')}")
    print("For each target: navigate CoC in the emulator to the described screen,")
    print("press 'r' here to refresh the screenshot, then drag+ENTER to cut it.\n")

    for name, hint in BUTTONS:
        path = os.path.join("assets", f"{name}.png")
        while True:
            disp = overview(img, f"[{name}]  {hint}")
            cv2.imshow("capture_templates (main window)", disp)
            k = cv2.waitKey(0) & 0xFF
            if k == ord("q"):
                cv2.destroyAllWindows()
                print("\nstopped early — rerun anytime, saved templates are kept.")
                return
            if k == ord("r"):
                img = grab()
                print("  screenshot refreshed")
                continue
            if k == ord("s"):
                print(f"  skipped {name}")
                break
            if k == 13 or k == 32:  # ENTER / SPACE
                if crop_and_save(img, path, name):
                    break

    print("\n-- digits: you will cut '0'..'9' IN ORDER from a loot number --")
    for ch in "0123456789":
        path = os.path.join("assets", "digits", f"{ch}.png")
        while True:
            disp = overview(img, f"[digit {ch}]  scout screen — drag ONLY the digit '{ch}' of a loot number")
            cv2.imshow("capture_templates (main window)", disp)
            k = cv2.waitKey(0) & 0xFF
            if k == ord("q"):
                cv2.destroyAllWindows()
                print("\nstopped early — rerun anytime, saved digits are kept.")
                return
            if k == ord("r"):
                img = grab()
                print("  screenshot refreshed")
                continue
            if k == ord("s"):
                print(f"  skipped digit {ch}")
                break
            if k == 13 or k == 32:
                if crop_and_save(img, path, f"digit {ch}"):
                    break

    print("\n-- loot boxes: drag around the WHOLE GOLD number --")
    while True:
        disp = overview(img, "[loot box]  scout screen — drag around the whole GOLD number")
        cv2.imshow("capture_templates (main window)", disp)
        k = cv2.waitKey(0) & 0xFF
        if k == ord("r"):
            img = grab()
            continue
        if k == ord("s") or k == ord("q"):
            break
        if k == 13 or k == 32:
            x, y, w, h = cv2.selectROI("drag around the GOLD number (ENTER=done, c=cancel)",
                                       img, False)
            cv2.destroyWindow("drag around the GOLD number (ENTER=done, c=cancel)")
            if w and h:
                bx, by, bw, bh = x / W, y / H, w / W, h / H
                print("\n# paste under 'vision:' in config.yaml")
                print("  loot_boxes:")
                print(f"    gold:   [{bx:.3f}, {by:.3f}, {bw:.3f}, {bh:.3f}]")
                print(f"    elixir: [{bx:.3f}, {by + 0.07:.3f}, {bw:.3f}, {bh:.3f}]")
                print(f"    dark:   [{bx:.3f}, {by + 0.14:.3f}, {bw:.3f}, {bh:.3f}]")
            break

    cv2.destroyAllWindows()
    print("\nDone. Verify with:  C:\\Python312\\python.exe main.py --once")


if __name__ == "__main__":
    main()
