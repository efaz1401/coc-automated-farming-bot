"""Screen vision: template matching + gold/elixir/DE digit reading.

Loot OCR pipeline (no extra deps):
  1. crop the loot strip (fractional box from config `vision.loot_boxes`)
  2. binarize + findContours to isolate digit glyphs
  3. merge horizontally-overlapping contours (hairline digits like "4")
  4. normalize each glyph to template height (aspect preserved)
  5. score vs each digit template with normalized cross-correlation
  6. sanity check: reject absurd readings (len > 7)
"""
from __future__ import annotations
import glob
import logging
import os
import cv2
import numpy as np

log = logging.getLogger("coc.vision")
DIGIT_HEIGHT = 24          # templates are normalized to this height
GLYPH_SCORE_MIN = 0.45     # min NCC score to accept a digit
MAX_DIGITS = 7             # 999,999 max — longer readings are garbage


class Vision:
    def __init__(self, cfg: dict, w: int = 1280, h: int = 720):
        self.cfg = cfg
        self.w, self.h = w, h
        self.templates: dict[str, np.ndarray] = {}
        self.template_dims: dict[str, tuple[int, int]] = {}
        self.threshold = cfg.get("vision", {}).get("match_threshold", 0.82)
        self.digits_folder = "assets/digits"
        self.reload_templates()
        vcfg = cfg.get("vision", {})
        self.loot_boxes = vcfg.get("loot_boxes", {
            "gold": [0.06, 0.10, 0.16, 0.06],
            "elixir": [0.06, 0.17, 0.16, 0.06],
            "dark": [0.06, 0.24, 0.16, 0.06],
        })
        self.hud_boxes = vcfg.get("hud_boxes", {
            "gold": [0.78, 0.045, 0.17, 0.055],
            "elixir": [0.78, 0.130, 0.17, 0.055],
            "dark": [0.78, 0.215, 0.17, 0.055],
        })

    # ---------- template management ----------
    def reload_templates(self):
        """Reload all template images and digit templates from disk."""
        self.templates.clear()
        self.template_dims.clear()
        self._load_templates(self.cfg.get("templates", {}))
        self.digits = self._load_digits(self.digits_folder)

    def _load_templates(self, paths: dict):
        for name, p in paths.items():
            if p and os.path.exists(p):
                img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    self.templates[name] = img
                    self.template_dims[name] = (img.shape[1], img.shape[0])

    def _load_digits(self, folder: str) -> dict[str, np.ndarray]:
        """Load digit PNGs, binarize, normalize to DIGIT_HEIGHT (aspect kept)."""
        digits: dict[str, np.ndarray] = {}
        if not os.path.isdir(folder):
            return digits
        for f in glob.glob(os.path.join(folder, "*.png")):
            key = os.path.splitext(os.path.basename(f))[0]
            img = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            _, bw = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY)
            cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                continue
            x, y, cw, ch = max((cv2.boundingRect(c) for c in cnts), key=lambda b: b[2] * b[3])
            glyph = bw[y:y + ch, x:x + cw]
            scale = DIGIT_HEIGHT / ch
            glyph = cv2.resize(glyph, (max(1, int(cw * scale)), DIGIT_HEIGHT))
            digits[key] = glyph
        return digits

    def get_template_status(self) -> dict[str, dict]:
        """Return diagnostic status for all configured templates."""
        tpl_cfg = self.cfg.get("templates", {})
        status = {}
        for name, path in tpl_cfg.items():
            exists = bool(path and os.path.exists(path))
            loaded = name in self.templates
            dims = self.template_dims.get(name)
            status[name] = {
                "path": path,
                "exists": exists,
                "loaded": loaded,
                "size": dims,
            }
        return status

    def get_digit_status(self) -> dict[str, bool]:
        """Return existence status for digits '0' through '9'."""
        return {str(d): str(d) in self.digits for d in range(10)}

    def missing_templates(self) -> list[str]:
        """Return list of template names that are not loaded."""
        tpl_cfg = self.cfg.get("templates", {})
        return [k for k in tpl_cfg if k not in self.templates]

    def find_near(self, gray: np.ndarray, name: str, cx: int, cy: int,
                  radius: int = 30, thresh: float = 0.75):
        """Template match restricted to a window around (cx, cy).
        Returns (cx_abs, cy_abs, score) of the best local match, or None."""
        tpl = self.templates.get(name)
        if tpl is None:
            return None
        th, tw = tpl.shape[:2]
        H, W = gray.shape[:2]
        x0 = max(0, cx - radius - tw // 2)
        y0 = max(0, cy - radius - th // 2)
        x1 = min(W, cx + radius + tw // 2)
        y1 = min(H, cy + radius + th // 2)
        roi = gray[y0:y1, x0:x1]
        if roi.shape[0] < th or roi.shape[1] < tw:
            return None
        res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score >= thresh:
            return (x0 + loc[0] + tw // 2, y0 + loc[1] + th // 2, float(score))
        return None

    def find(self, screen_gray: np.ndarray, name: str, threshold: float | None = None, thresh: float | None = None):
        """Return (cx, cy, score) or None."""
        tpl = self.templates.get(name)
        if tpl is None:
            return None
        th, tw = tpl.shape[:2]
        sh, sw = screen_gray.shape[:2]
        if th > sh or tw > sw:
            return None
        res = cv2.matchTemplate(screen_gray, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        effective_thresh = threshold if threshold is not None else (thresh if thresh is not None else self.threshold)
        if score >= effective_thresh:
            return (loc[0] + tw // 2, loc[1] + th // 2, float(score))
        return None

    def find_all_matches(self, screen_gray: np.ndarray) -> dict[str, dict]:
        """Scan current screen for all loaded templates and return locations + scores."""
        found = {}
        for name, tpl in self.templates.items():
            th, tw = tpl.shape[:2]
            sh, sw = screen_gray.shape[:2]
            if th > sh or tw > sw:
                continue
            res = cv2.matchTemplate(screen_gray, tpl, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(res)
            if score >= self.threshold:
                found[name] = {
                    "cx": loc[0] + tw // 2,
                    "cy": loc[1] + th // 2,
                    "x": loc[0],
                    "y": loc[1],
                    "w": tw,
                    "h": th,
                    "score": float(score),
                }
        return found

    # ---------- loot OCR ----------
    @staticmethod
    def _merge_boxes(boxes, max_digit_w: int = 20):
        """Merge contour fragments that belong to the same glyph (e.g. split '4').
        Preserves distinct adjacent digits."""
        if not boxes:
            return []
        boxes = sorted(boxes, key=lambda b: b[0])
        merged = [boxes[0]]
        for bx, by, bw, bh in boxes[1:]:
            px, py, pw, ph = merged[-1]
            nx = min(px, bx)
            ny = min(py, by)
            nw = max(px + pw, bx + bw) - nx
            nh = max(py + ph, by + bh) - ny

            is_overlap = bx < px + pw
            is_hairline = (pw <= 3 or bw <= 3) and (bx <= px + pw + 2)
            if nw <= max_digit_w and (is_overlap or is_hairline):
                merged[-1] = (nx, ny, nw, nh)
            else:
                merged.append((bx, by, bw, bh))
        return merged

    def _best_digit(self, glyph_bw: np.ndarray):
        """Score a binarized glyph against all digit templates via NCC."""
        best, best_s = "", -1.0
        for d, tpl in self.digits.items():
            # aspect-preserving resize to template height, pad/crop width
            scale = tpl.shape[0] / glyph_bw.shape[0]
            rw = max(1, int(glyph_bw.shape[1] * scale))
            g = cv2.resize(glyph_bw, (rw, tpl.shape[0]))
            if rw < tpl.shape[1]:      # pad narrow glyph with black
                g = cv2.copyMakeBorder(g, 0, 0, 0, tpl.shape[1] - rw, cv2.BORDER_CONSTANT)
            elif rw > tpl.shape[1]:
                g = cv2.resize(g, (tpl.shape[1], tpl.shape[0]))
            s = float(cv2.matchTemplate(tpl, g, cv2.TM_CCOEFF_NORMED)[0][0])
            if s > best_s:
                best, best_s = d, s
        return (best, best_s) if best_s >= GLYPH_SCORE_MIN else ("", -1.0)

    def _read_number_strip(self, img_or_gray: np.ndarray, box) -> int:
        """Read an integer from a fractional (x, y, w, h) region. -1 = unread."""
        if not self.digits:
            return -1
        H, W = img_or_gray.shape[:2]
        x, y, w, h = int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)
        crop = img_or_gray[y:y + h, x:x + w]
        if crop.size == 0:
            return -1

        # White text isolation: in CoC, digits are white text (high in all channels).
        # min across channels cancels out bright colored backgrounds (yellow gold bar, magenta elixir bar).
        if crop.ndim == 3:
            min_ch = np.min(crop, axis=2)
        else:
            min_ch = crop

        # Primary fixed threshold for crisp white text
        _, th = cv2.threshold(min_ch, 165, 255, cv2.THRESH_BINARY)
        cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        raw = [cv2.boundingRect(c) for c in cnts if c is not None]

        # Otsu fallback if fixed threshold found nothing
        if not raw:
            _, th = cv2.threshold(min_ch, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            raw = [cv2.boundingRect(c) for c in cnts if c is not None]

        if not raw:
            return -1

        # Filter: keep glyphs that resemble digit heights (10px to 36px in 1280x720)
        candidates = [b for b in raw if 10 <= b[3] <= 36 and b[2] >= 3]
        if candidates:
            max_h = max(b[3] for b in candidates)
            boxes = [b for b in candidates if b[3] >= max_h * 0.55]
        else:
            max_h = max(b[3] for b in raw)
            boxes = [b for b in raw if b[3] >= max_h * 0.50 and b[2] >= 3]

        out = ""
        for (bx, by, bw, bh) in self._merge_boxes(boxes):
            digit, _s = self._best_digit(th[by:by + bh, bx:bx + bw])
            if not digit:
                return -1          # unknown glyph -> whole reading untrustworthy
            out += digit
        if not out or len(out) > MAX_DIGITS:
            return -1
        try:
            return int(out)
        except ValueError:
            return -1

    def read_village_resources(self, screen_bgr: np.ndarray) -> dict:
        """Return player's own village storage resources {'gold':int,'elixir':int,'dark':int} (-1 = unread)."""
        return {k: self._read_number_strip(screen_bgr, box)
                for k, box in self.hud_boxes.items()}

    def read_scout_loot(self, screen_bgr: np.ndarray) -> dict:
        """Return enemy village available loot on scout screen {'gold':int,'elixir':int,'dark':int} (-1 = unread)."""
        return {k: self._read_number_strip(screen_bgr, box)
                for k, box in self.loot_boxes.items()}

    def read_loot(self, screen_bgr: np.ndarray) -> dict:
        """Intelligently read resources: returns scout loot if on attack screen, otherwise village HUD resources."""
        scout = self.read_scout_loot(screen_bgr)
        if scout.get("gold", -1) >= 0 or scout.get("elixir", -1) >= 0:
            return scout
        hud = self.read_village_resources(screen_bgr)
        if hud.get("gold", -1) >= 0 or hud.get("elixir", -1) >= 0:
            return hud
        return scout

    # ---------- storage fill bars ----------
    # CoC HUD resource bars fill from the RIGHT (icon side) towards the left:
    # verified on live client (1924 gold => yellow occupies the right ~17%).
    # We find the LEFTMOST column matching the resource color; fill ratio =
    # (width - leftmost) / width. White value text (sat=0) never matches.
    STORAGE_DEFAULTS = {
        "gold":   {"box": [0.788, 0.042, 0.150, 0.032], "hsv_lo": [15, 170, 170], "hsv_hi": [42, 255, 255]},
        "elixir": {"box": [0.788, 0.128, 0.150, 0.032], "hsv_lo": [138, 100, 120], "hsv_hi": [170, 255, 255]},
        "dark":   {"box": [0.788, 0.214, 0.150, 0.032], "hsv_lo": [130, 60, 15],  "hsv_hi": [175, 255, 90]},
    }

    def read_storage_fill(self, screen_bgr: np.ndarray) -> dict[str, float]:
        """Return {'gold': r, 'elixir': r, 'dark': r} fill ratios 0.0-1.0.
        -1.0 means the bar region was unreadable. Config override via
        vision.storage_bars.<name> = {box, hsv_lo, hsv_hi, anchor}."""
        out: dict[str, float] = {}
        cfg_bars = self.cfg.get("vision", {}).get("storage_bars", {}) or {}
        hsv = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2HSV)
        H, W = hsv.shape[:2]
        for name, dflt in self.STORAGE_DEFAULTS.items():
            spec = dict(dflt)
            spec.update(cfg_bars.get(name, {}) or {})
            bx, by, bw, bh = spec["box"]
            x0, y0 = int(bx * W), int(by * H)
            crop = hsv[y0:int((by + bh) * H), x0:int((bx + bw) * W)]
            if crop.size == 0:
                out[name] = -1.0
                continue
            mask = cv2.inRange(crop,
                               np.array(spec["hsv_lo"], np.uint8),
                               np.array(spec["hsv_hi"], np.uint8))
            col_has = (mask > 0).any(axis=0)
            if not col_has.any():
                out[name] = 0.0
                continue
            anchor = spec.get("anchor", "right")
            if anchor == "left":
                rightmost = int(np.max(np.nonzero(col_has)[0]))
                out[name] = round((rightmost + 1) / mask.shape[1], 3)
            else:  # right-anchored fill (CoC default)
                leftmost = int(np.min(np.nonzero(col_has)[0]))
                out[name] = round((mask.shape[1] - leftmost) / mask.shape[1], 3)
        return out
