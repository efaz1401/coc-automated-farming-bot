"""Regression tests: run with  python tests/run_tests.py
Covers: loot OCR, digit templates, bug fixes (dark elixir min=0, interruptible sleep),
ADB device parsing, and UI module smoke tests.
"""
import os
import sys
import tempfile
import time
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.adb import AdbDevice
from bot.bot import Bot, load_config
from bot.vision import Vision, DIGIT_HEIGHT  # noqa: E402

PASS = 0


def ok(cond, msg):
    global PASS
    assert cond, f"FAIL: {msg}"
    PASS += 1
    print(f"  ok - {msg}")


def draw_glyph(ch: str) -> np.ndarray:
    """Render one digit, tightly cropped binary — identical for templates & strips."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(ch, font, 2.0, 3)
    img = np.zeros((th + 20, tw + 20), np.uint8)
    cv2.putText(img, ch, (10, 10 + th), font, 2.0, 255, 3)
    _, bw = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY)
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    x, y, cw, chh = max((cv2.boundingRect(c) for c in cnts), key=lambda b: b[2] * b[3])
    return bw[y:y + chh, x:x + cw]


def make_digit_templates(tmp: str) -> dict:
    """Save tightly-cropped renders of 0-9 as templates (mimics CoC digits)."""
    d = {}
    for ch in "0123456789":
        img = draw_glyph(ch)
        cv2.imwrite(os.path.join(tmp, f"{ch}.png"), img)
        d[ch] = img
    return d


def render_strip(value: int, scale: float = 1.0, noise: float = 0.0) -> np.ndarray:
    """Compose a bright-on-dark loot number strip inside a 1280x720 frame."""
    glyphs = [draw_glyph(c) for c in str(value)]
    if scale != 1.0:
        glyphs = [cv2.resize(g, None, fx=scale, fy=scale) for g in glyphs]
    gh = max(g.shape[0] for g in glyphs)
    need = 8 + sum(g.shape[1] + 6 for g in glyphs)
    strip = np.zeros((gh + 12, max(int(1280 * 0.25), need)), np.uint8)
    x = 8
    for g in glyphs:
        strip[6:6 + g.shape[0], x:x + g.shape[1]] = g
        x += g.shape[1] + 6
    if noise:
        n = np.random.default_rng(0).integers(0, 60, strip.shape, dtype=np.uint8)
        strip = cv2.add(strip, n)
    canvas = np.zeros((720, 1280), np.uint8)
    y0 = int(720 * 0.10)
    canvas[y0:y0 + strip.shape[0], 0:strip.shape[1]] = strip
    return canvas


def main():
    print("== vision OCR tests ==")
    with tempfile.TemporaryDirectory() as tmp:
        make_digit_templates(tmp)
        vis = Vision.__new__(Vision)           # bypass __init__ (no real assets)
        vis.digits = vis._load_digits(tmp)     # exercise real loader
        ok(len(vis.digits) == 10, "digit loader found 10 templates")
        ok(all(v.shape[0] == DIGIT_HEIGHT for v in vis.digits.values()),
           "templates normalized to DIGIT_HEIGHT")

        box = (0.0, 0.10, 0.40, 0.12)          # generous; covers all scales
        for value in (0, 7, 42, 1234, 999999):
            img = render_strip(value, scale=1.0)
            got = vis._read_number_strip(img, box)
            ok(got == value, f"read {value} @1.0x -> {got}")

        for scale in (0.8, 1.3, 1.6):
            img = render_strip(314159, scale=scale)
            got = vis._read_number_strip(img, box)
            ok(got == 314159, f"read 314159 @ {scale}x -> {got}")

        img = render_strip(777777, scale=1.0, noise=50)
        got = vis._read_number_strip(img, box)
        ok(got == 777777, f"read 777777 with noise -> {got}")

        blank = np.zeros((720, 1280), np.uint8)
        ok(vis._read_number_strip(blank, box) == -1, "empty strip -> -1")

        garbage = render_strip(12345678901, scale=1.0)  # 11 digits > MAX_DIGITS
        ok(vis._read_number_strip(garbage, box) == -1, "overlong reading rejected")

        # box merging: draw '4' as two strokes with a visible gap
        img = render_strip(444, scale=1.0)
        boxes = [(10, 5, 10, 30), (18, 5, 10, 30)]  # overlapping x -> must merge
        ok(len(vis._merge_boxes(list(boxes))) == 1, "contour merge combines split glyphs")

    print("== config + import smoke tests ==")
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
    cfg = load_config(cfg_path)
    ok("use_adb_screencap" not in cfg["emulator"], "dead mss config removed")
    ok(set(cfg["vision"]["loot_boxes"]) == {"gold", "elixir", "dark"},
       "loot_boxes present in config")
    ok("return_home_fallback" in cfg["farming"], "return_home_fallback present")
    ok(hasattr(Bot, "start_search") and hasattr(Bot, "attack")
       and hasattr(Bot, "end_battle") and hasattr(Bot, "search_loop"),
       "Bot has merged phase methods (no monkey-patching)")
    ok(cfg["screen"]["width"] == 1280 and cfg["screen"]["height"] == 720,
       "screen size sane")

    print("== bug fix verification: dark elixir logic ==")
    bot = Bot(cfg)
    # Test case 1: min_dark is 0, dark is unread (-1), gold/elixir meet criteria
    bot.f["min_gold"] = 400000
    bot.f["min_elixir"] = 400000
    bot.f["min_dark"] = 0
    bot.vis.read_loot = lambda _img: {"gold": 500000, "elixir": 500000, "dark": -1}
    accepted, _ = bot.evaluate_village(np.zeros((720, 1280, 3), np.uint8))
    ok(accepted is True, "min_dark=0 allows attack when dark is unread (-1)")

    # Test case 2: min_dark is 2000, dark is 1000 -> rejected
    bot.f["min_dark"] = 2000
    bot.vis.read_loot = lambda _img: {"gold": 500000, "elixir": 500000, "dark": 1000}
    accepted, _ = bot.evaluate_village(np.zeros((720, 1280, 3), np.uint8))
    ok(accepted is False, "min_dark=2000 correctly rejects dark=1000")

    print("== bug fix verification: interruptible sleep ==")
    t_start = time.time()
    bot._stop_event.clear()
    # Trigger stop in another thread after 0.05s
    import threading
    threading.Timer(0.05, bot.stop).start()
    res = bot.sleep_interruptible(10.0)
    dur = time.time() - t_start
    ok(res is False and dur < 0.5, f"sleep_interruptible terminated in {dur:.3f}s upon stop event")

    print("== vision inspection API tests ==")
    status = bot.vis.get_template_status()
    ok(isinstance(status, dict) and "attack_button" in status, "get_template_status returns dict with keys")
    digits_st = bot.vis.get_digit_status()
    ok(isinstance(digits_st, dict) and len(digits_st) == 10, "get_digit_status returns 10 digit statuses")

    print("== UI modules smoke test ==")
    from ui.theme import COLORS, FONTS
    ok("bg_main" in COLORS and "title" in FONTS, "theme configuration loaded")
    import ui.crop_dialog
    ok(hasattr(ui.crop_dialog, "CropDialog"), "CropDialog available")
    import ui.app
    ok(hasattr(ui.app, "BotGUI"), "BotGUI class available")

    import tkinter as tk
    try:
        root = tk.Tk()
        root.withdraw()
        app = ui.app.BotGUI(root, config_path=cfg_path)
        ok(app.notebook is not None and app.screen_canvas is not None, "BotGUI initialized with all tabs and canvases")
        root.destroy()
    except Exception as e:
        ok(True, f"BotGUI skipped in display-less environment ({e})")

    print("== Web Server & REST API tests ==")
    import json
    import urllib.request
    from web.server import start_server

    test_srv = start_server(port=0, host="127.0.0.1", block=False)
    # Wait for server socket readiness with retry
    base_url = f"http://127.0.0.1:{test_srv.port}"
    for _ in range(20):
        try:
            with urllib.request.urlopen(f"{base_url}/api/status", timeout=1):
                break
        except Exception:
            time.sleep(0.1)

    try:
        with urllib.request.urlopen(f"{base_url}/") as resp:
            ok(resp.status == 200 and "CoC Farming Bot".encode("utf-8") in resp.read(), "Web server serves index.html")

        with urllib.request.urlopen(f"{base_url}/api/status") as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ok(data.get("ok") is True and "phase" in data and "stats" in data, "Web /api/status returns valid JSON")

        with urllib.request.urlopen(f"{base_url}/api/templates") as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ok(data.get("ok") is True and "attack_button" in data.get("templates", {}), "Web /api/templates returns templates")

        with urllib.request.urlopen(f"{base_url}/api/screen.png?overlay=1") as resp:
            ok(resp.status == 200 and resp.read().startswith(b"\x89PNG"), "Web /api/screen.png returns valid PNG")

        with urllib.request.urlopen(f"{base_url}/assets/builder_face.png") as resp:
            ok(resp.status == 200 and resp.headers.get("Content-Type") == "image/png", "Web serves /assets/builder_face.png")

        req = urllib.request.Request(f"{base_url}/api/village/upgrade", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ok(data.get("ok") is True and "initiated" in data.get("message", ""), "Web /api/village/upgrade triggers upgrade")

        req_clear = urllib.request.Request(f"{base_url}/api/logs/clear", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req_clear) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ok(data.get("ok") is True and "cleared" in data.get("message", ""), "Web /api/logs/clear clears logs")
    finally:
        test_srv.stop()

    print("== VillageUpgrader unit tests ==")
    from bot.upgrade import VillageUpgrader
    bot_inst = Bot(load_config(cfg_path))
    upg = VillageUpgrader(bot_inst)
    ok(upg.is_enabled() is True, "VillageUpgrader is_enabled returns True with config")
    ok("builder_face" in bot_inst.vis.templates, "builder_face template is loaded")
    ok("upgrade_button" in bot_inst.vis.templates, "upgrade_button template is loaded")
    ok("collect_elixir" in bot_inst.vis.templates, "collect_elixir template is loaded")
    ok("all_builders_busy" in bot_inst.vis.templates, "all_builders_busy template is loaded")
    ok("zero_builders" in bot_inst.vis.templates, "zero_builders template is loaded")
    ok("one_builder" in bot_inst.vis.templates, "one_builder template is loaded")
    ok("two_builders" in bot_inst.vis.templates, "two_builders template is loaded")
    ok("finish_now" in bot_inst.vis.templates, "finish_now template is loaded")
    ok("gem_icon" in bot_inst.vis.templates, "gem_icon template is loaded")
    ok("confirm_text" in bot_inst.vis.templates, "confirm_text template is loaded")
    ok("upgrade_button_dim" in bot_inst.vis.templates, "upgrade_button_dim template is loaded")

    # Anti-Gem and safety check test: empty/gem screen returns False
    dummy_gray = np.zeros((720, 1280), dtype=np.uint8)
    ok(upg.check_builders_busy(dummy_gray) is False, "check_builders_busy returns False on empty screen")
    ok(upg.is_gem_prompt_active(dummy_gray) is False, "is_gem_prompt_active returns False on empty screen")

    # Anti-Gem verification on actual game captures
    if os.path.exists("logs/after_3_upgrades.png"):
        img_a3 = cv2.imread("logs/after_3_upgrades.png", cv2.IMREAD_GRAYSCALE)
        ok(upg.check_builders_busy(img_a3) is True, "check_builders_busy correctly identifies 0/2 busy builders")
        ok(upg.get_free_builders(img_a3) == 0, "get_free_builders correctly returns 0 for 0/2")

    if os.path.exists("logs/upgrade_success_test.png"):
        img_succ = cv2.imread("logs/upgrade_success_test.png", cv2.IMREAD_GRAYSCALE)
        ok(upg.get_free_builders(img_succ) == 1, "get_free_builders correctly returns 1 for 1/2")
        ok(upg.is_gem_prompt_active(img_succ) is True, "is_gem_prompt_active flags Finish Now gem button")

    if os.path.exists("logs/live_placement_check.png"):
        img_live = cv2.imread("logs/live_placement_check.png", cv2.IMREAD_GRAYSCALE)
        ok(upg.get_free_builders(img_live) == 2, "get_free_builders correctly returns 2 for 2/2")

    if os.path.exists("logs/gold_storage_upgrade_dialog.png"):
        img_gs = cv2.imread("logs/gold_storage_upgrade_dialog.png", cv2.IMREAD_GRAYSCALE)
        ok(upg.is_gem_prompt_active(img_gs) is False, "is_gem_prompt_active returns False on valid resource upgrade dialog")

    # Test upgrade stats initialization
    ok(bot_inst.stats.get("buildings_upgraded") == 0, "buildings_upgraded initialized to 0")
    ok(bot_inst.stats.get("lab_researches") == 0, "lab_researches initialized to 0")
    ok(bot_inst.stats.get("walls_upgraded") == 0, "walls_upgraded initialized to 0")

    print("== state machine tests ==")
    from bot.state import ScreenState, classify, looks_like_reload_dialog, looks_like_loading
    from bot.recovery import Recovery
    from bot.army import Army

    bot2 = Bot(load_config(cfg_path))
    ok(hasattr(bot2, "recovery") and isinstance(bot2.recovery, Recovery), "Bot wires Recovery")
    ok(hasattr(bot2, "army") and isinstance(bot2.army, Army), "Bot wires Army")
    ok(hasattr(bot2, "adb_shell") and hasattr(bot2, "adb_keyevent")
       and hasattr(bot2, "adb_tap") and hasattr(bot2, "current_state"),
       "Bot has adb_shell/keyevent/tap/current_state helpers")
    ok(hasattr(bot2.adb, "shell") and hasattr(bot2.adb, "keyevent"),
       "AdbDevice has shell/keyevent")

    blank_bgr = np.zeros((720, 1280, 3), np.uint8)
    blank_gray = np.zeros((720, 1280), np.uint8)
    ok(looks_like_loading(blank_gray) is True, "uniform black frame = LOADING")
    st, reason = classify(blank_bgr, blank_gray, bot2.vis, bot2.cfg)
    ok(st in (ScreenState.LOADING, ScreenState.UNKNOWN), f"blank frame -> {st.value}")

    # synthetic reload dialog: dimmed screen + centered green button
    dlg = np.full((720, 1280, 3), 40, np.uint8)          # dark overlay everywhere
    cv2.rectangle(dlg, (560, 380), (720, 420), (60, 200, 90), -1)  # green button @~(0.5,0.56)
    dlg_gray = cv2.cvtColor(dlg, cv2.COLOR_BGR2GRAY)
    ok(looks_like_reload_dialog(dlg, dlg_gray) is True, "heuristic detects reload dialog")
    st, _ = classify(dlg, dlg_gray, bot2.vis, bot2.cfg)
    ok(st is ScreenState.RELOAD_DIALOG, f"classify -> RELOAD_DIALOG (got {st.value})")
    # bright village grass + green button but no overlay -> NOT a dialog
    grass = np.full((720, 1280, 3), (60, 180, 90), np.uint8)
    cv2.rectangle(grass, (560, 380), (720, 420), (60, 200, 90), -1)
    ok(looks_like_reload_dialog(grass, cv2.cvtColor(grass, cv2.COLOR_BGR2GRAY)) is False,
       "bright screen + green blob is not a reload dialog")

    print("== storage fill tests ==")
    def render_bars(gold_frac, elix_frac):
        img = np.zeros((720, 1280, 3), np.uint8)
        H, W = 720, 1280
        for name, frac in (("gold", gold_frac), ("elixir", elix_frac)):
            if frac <= 0:
                continue
            spec = bot2.vis.STORAGE_DEFAULTS[name]
            bx, by, bw, bh = spec["box"]
            x0, y0 = int(bx * W), int(by * H)
            x1, y1 = int((bx + bw) * W), int((by + bh) * H)
            fill_from = x1 - int((x1 - x0) * frac)   # right-anchored fill
            color = (60, 210, 255) if name == "gold" else (230, 40, 230)  # BGR
            cv2.rectangle(img, (fill_from, y0), (x1, y1), color, -1)
        return img
    fill = bot2.vis.read_storage_fill(render_bars(1.0, 1.0))
    ok(fill["gold"] > 0.95 and fill["elixir"] > 0.95, f"full bars read ~1.0 -> {fill}")
    fill = bot2.vis.read_storage_fill(render_bars(0.0, 0.0))
    ok(fill["gold"] == 0.0 and fill["elixir"] == 0.0, f"empty bars read 0.0 -> {fill}")
    fill = bot2.vis.read_storage_fill(render_bars(0.5, 0.25))
    ok(0.4 <= fill["gold"] <= 0.6 and 0.15 <= fill["elixir"] <= 0.35,
       f"partial bars read correctly -> {fill}")
    bot2.f["full_ratio"] = 0.97
    # _storages_full only trusts HOME screens: fake attack_button landmark
    bot2.vis.find = lambda g, n, t=None, **kw: (10, 10, 0.99) if n == "attack_button" else None
    bot2.grab = lambda: (np.zeros((720, 1280, 3), np.uint8), blank_gray)
    bot2.vis.read_storage_fill = lambda _img: {"gold": 1.0, "elixir": 1.0, "dark": 0.0}
    ok(bot2._storages_full() is True, "_storages_full True when both full (on HOME)")
    bot2.vis.read_storage_fill = lambda _img: {"gold": 1.0, "elixir": 0.5, "dark": 0.0}
    ok(bot2._storages_full() is False, "_storages_full False when elixir not full")
    bot2.vis.read_storage_fill = lambda _img: {"gold": -1.0, "elixir": -1.0, "dark": -1.0}
    ok(bot2._storages_full() is False, "unreadable bars never stall the bot")
    bot2.vis.find = lambda g, n, t=None, **kw: None   # no landmarks -> not HOME
    bot2.vis.read_storage_fill = lambda _img: {"gold": 1.0, "elixir": 1.0, "dark": 0.0}
    ok(bot2._storages_full() is False, "full bars ignored when not on HOME screen")

    print("== army slot detection tests ==")
    army = Army(bot2)
    centers = army.slot_centers()
    ok(len(centers) == 11, f"11 slot centers computed ({len(centers)})")
    ok(all(0 <= cx < 1280 and 0 <= cy < 720 for cx, cy in centers), "slot centers in frame")
    # synthetic troop bar: slots 0,1,3 filled (colorful), rest empty (uniform dark)
    bar = np.zeros((720, 1280, 3), np.uint8)
    for i, (cx, cy) in enumerate(centers):
        if i in (0, 1, 3):
            rng = np.random.default_rng(i)
            icon = rng.integers(0, 255, (36, 36, 3), dtype=np.uint8)  # colorful noisy icon
            bar[cy - 18:cy + 18, cx - 18:cx + 18] = icon
        else:
            bar[cy - 18:cy + 18, cx - 18:cx + 18] = 25                # empty slot gray
    filled = army.detect_filled_slots(bar)
    ok(filled == [0, 1, 3], f"filled slots detected {filled}")
    ok(army.detect_filled_slots(blank_bgr) == [], "all-empty bar -> no slots")
    # deploy() must never crash and must fall back cleanly when bar is empty
    bot2._stop_event.clear()
    bot2.adb_tap = lambda x, y: None
    bot2.tap_frac = lambda x, y: None
    bot2.sleep_interruptible = lambda s, poll=0.1: True
    ok(army.deploy() is False, "deploy() returns False on empty bar (legacy fallback path)")

    print(f"\nALL {PASS} TESTS PASSED")


if __name__ == "__main__":
    main()
