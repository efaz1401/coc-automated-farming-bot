"""Dynamic army-bar detection and deployment.

Cracked from the reference bot's `detect_troop_slots`/`deploy_brutal`:
the troop bar is a fixed grid of slots; each slot is "filled" if its icon
patch is colorful/high-variance (empty slots are uniform dark translucent).
An optional `empty_slot` template overrides the heuristic when available.

Deploy uses long-press swipe-holds at configured points (drops a continuous
wave instead of N discrete taps), with per-point jitter and human pacing.
"""
from __future__ import annotations
import logging
import random
import numpy as np

log = logging.getLogger("coc.army")

DEFAULTS = {
    "slot_start_x_frac": 0.131,   # center of slot 0  (168px @1280)
    "slot_step_x_frac": 0.0453,   # slot pitch        (58px  @1280)
    "slot_count": 11,
    "patch_px": 18,               # half-size of the sampled icon patch
    "min_colorfulness": 22.0,     # mean channel spread (max-min) to be "filled"
    "min_stddev": 14.0,           # luminance stddev to be "filled"
    "hold_ms": 1400,              # swipe-hold duration per deploy point
    "skip_last_slots": 0,         # e.g. 1 to keep a spell slot unused
}


class Army:
    def __init__(self, bot):
        self.bot = bot

    @property
    def acfg(self) -> dict:
        cfg = dict(DEFAULTS)
        cfg.update(self.bot.cfg.get("army", {}) or {})
        return cfg

    # ---------- detection ----------
    def slot_centers(self) -> list[tuple[int, int]]:
        """Pixel centers of every bar slot, from fractional grid config."""
        c = self.acfg
        W, H = self.bot.W, self.bot.H
        by = self.bot.f["troops"].get("troop_bar_y", 0.90)
        out = []
        for i in range(int(c["slot_count"])):
            cx = int((c["slot_start_x_frac"] + i * c["slot_step_x_frac"]) * W)
            out.append((cx, int(by * H)))
        return out

    @staticmethod
    def slot_is_filled(img: np.ndarray, cx: int, cy: int, half: int,
                       min_color: float, min_std: float) -> bool:
        h, w = img.shape[:2]
        x0, x1 = max(0, cx - half), min(w, cx + half)
        y0, y1 = max(0, cy - half), min(h, cy + half)
        patch = img[y0:y1, x0:x1]
        if patch.size == 0:
            return False
        if patch.ndim == 3:
            mx = patch.max(axis=2).astype(float)
            mn = patch.min(axis=2).astype(float)
            colorful = float((mx - mn).mean())
            std = float(patch.mean(axis=2).std())
        else:
            colorful = 0.0
            std = float(patch.std())
        return colorful >= min_color or std >= min_std

    def detect_filled_slots(self, img: np.ndarray) -> list[int]:
        """Indices of filled troop slots. Prefers the empty_slot template:
        a slot whose center matches 'empty_slot' strongly is empty; otherwise
        the colorfulness/stddev heuristic decides."""
        c = self.acfg
        gray = None
        tpl = self.bot.vis.templates.get("empty_slot")
        filled: list[int] = []
        for i, (cx, cy) in enumerate(self.slot_centers()):
            if tpl is not None:
                if gray is None:
                    import cv2
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                m = self.bot.vis.find_near(gray, "empty_slot", cx, cy,
                                           radius=int(c["patch_px"] * 1.5),
                                           thresh=0.60)
                if m is not None:
                    continue  # matched empty art -> slot is empty
            if self.slot_is_filled(img, cx, cy, int(c["patch_px"]),
                                   float(c["min_colorfulness"]),
                                   float(c["min_stddev"])):
                filled.append(i)
        log.info("troop bar: %d/%d slots filled -> %s",
                 len(filled), int(c["slot_count"]), filled)
        return filled

    # ---------- deployment ----------
    def deploy(self) -> bool:
        """Deploy all filled slots at configured points. Returns True if any
        troop was deployed. Falls back to legacy fixed-slot taps if the bar
        scan finds nothing (never leaves the battle silent)."""
        bot = self.bot
        c = self.acfg
        pts = bot.f["deploy_points"]
        iv = bot.f["troops"]["drop_interval_sec"]
        jitter = bot.t.get("jitter_px", 4)

        try:
            img, _ = bot.grab()
            slots = self.detect_filled_slots(img)
        except Exception as e:
            log.warning("slot detection failed (%s) — legacy fallback", e)
            slots = []

        skip = int(c.get("skip_last_slots", 0))
        if skip and slots:
            slots = slots[:-skip] or slots

        if not slots:
            log.warning("no filled slots detected — using legacy 3-slot deploy")
            return False

        centers = self.slot_centers()
        hold = int(c["hold_ms"])
        for si in slots:
            if bot._stop_event.is_set():
                return True
            sx, sy = centers[si]
            bot.adb_tap(sx, sy)                      # select the slot
            bot.sleep_interruptible(random.uniform(0.25, 0.5))
            for (px, py) in pts:
                if bot._stop_event.is_set():
                    return True
                x = bot.fx(px) + random.randint(-jitter * 2, jitter * 2)
                y = bot.fy(py) + random.randint(-jitter * 2, jitter * 2)
                # swipe-hold in place = continuous troop stream at that point
                bot.adb.swipe(x, y, x + random.randint(-6, 6),
                              y + random.randint(-6, 6), ms=hold)
                bot.sleep_interruptible(random.uniform(iv[0], iv[1]))
        return True
