"""Screen-state classifier: the foundation of a reliable bot.

Instead of blindly assuming which screen CoC is on, every decision point calls
classify() and routes accordingly. Templates are preferred; template-free
heuristics (green dialog button + darkened overlay) cover the disconnect /
reload / "anyone there?" dialogs which cannot be pre-captured.

Priority order matters: a battle-end screen still shows the surrender template
in some clients, so BATTLE_END is checked before BATTLE, etc.
"""
from __future__ import annotations
import enum
import logging
import numpy as np

log = logging.getLogger("coc.state")


class ScreenState(enum.Enum):
    HOME = "home_village"            # own village, Attack! button visible
    ATTACK_MENU = "attack_menu"      # Find a Match panel
    CLOUDS = "clouds"                # matchmaking / searching opponents
    SCOUT = "scout"                  # enemy village shown, Next button visible
    BATTLE = "battle"                # fight running, Surrender visible
    BATTLE_END = "battle_end"        # victory/defeat screen, Return Home visible
    RELOAD_DIALOG = "reload_dialog"  # connection lost / reload / inactivity popup
    LOADING = "loading"              # mostly-uniform loading splash
    UNKNOWN = "unknown"


def _green_button_score(img: np.ndarray, fx: float, fy: float, rad: int = 6) -> float:
    """Fraction of green-ish pixels in a small patch (dialog confirm buttons)."""
    h, w = img.shape[:2]
    cx, cy = int(fx * w), int(fy * h)
    x0, x1 = max(0, cx - rad * 3), min(w, cx + rad * 3)
    y0, y1 = max(0, cy - rad), min(h, cy + rad)
    patch = img[y0:y1, x0:x1]
    if patch.size == 0:
        return 0.0
    b, g, r = patch[:, :, 0].astype(int), patch[:, :, 1].astype(int), patch[:, :, 2].astype(int)
    green = (g > 110) & (g > r + 25) & (g > b + 40)
    return float(green.mean())


def _patch_mean(gray: np.ndarray, fx: float, fy: float, fw: float, fh: float) -> float:
    h, w = gray.shape[:2]
    x0, y0 = int(fx * w), int(fy * h)
    crop = gray[y0:int((fy + fh) * h), x0:int((fx + fw) * w)]
    return float(crop.mean()) if crop.size else -1.0


def looks_like_reload_dialog(img: np.ndarray, gray: np.ndarray,
                             green_frac=(0.50, 0.56)) -> bool:
    """Template-free detection of CoC's centered confirm dialogs
    (Connection lost / Reload / inactivity). They all share:
      - a dimmed full-screen overlay (edges go dark)
      - one centered green button ~56% down the screen
    """
    if _green_button_score(img, *green_frac) < 0.25:
        return False
    # overlay check: the village top strip (normally bright HUD/sky) goes dim
    edge = _patch_mean(gray, 0.02, 0.30, 0.05, 0.20)
    if edge < 0 or edge > 120:        # bright grass means no overlay
        return False
    return True


def looks_like_loading(gray: np.ndarray) -> bool:
    """CoC loading splash: very low variance over most of the frame."""
    h, w = gray.shape[:2]
    center = gray[int(0.2 * h):int(0.8 * h), int(0.2 * w):int(0.8 * w)]
    if center.size == 0:
        return False
    return float(center.std()) < 8.0


def classify(img: np.ndarray, gray: np.ndarray, vis, cfg: dict | None = None
             ) -> tuple[ScreenState, str]:
    """Classify the current screen. Returns (state, reason). Never raises."""
    cfg = cfg or {}
    st_cfg = cfg.get("states", {}) if isinstance(cfg, dict) else {}
    th = float(st_cfg.get("match_threshold", 0.78))

    def has(name: str, t: float = th) -> bool:
        try:
            return vis.find(gray, name, t) is not None
        except Exception:
            return False

    # 1. Battle-end first (some clients keep surrender art behind the banner)
    if has("return_home"):
        return ScreenState.BATTLE_END, "return_home visible"
    # 2. Active battle
    if has("surrender_button"):
        return ScreenState.BATTLE, "surrender_button visible"
    # 3. Disconnect / reload / inactivity dialogs
    if has("reload_button", 0.75) or has("try_again", 0.75) or has("reload_dialog", 0.75):
        return ScreenState.RELOAD_DIALOG, "reload/try_again template"
    green_frac = tuple(st_cfg.get("dialog_button_frac", [0.50, 0.56]))
    if looks_like_reload_dialog(img, gray, green_frac):
        return ScreenState.RELOAD_DIALOG, "green-button+overlay heuristic"
    # 4. Scouting an enemy village
    if has("next_button"):
        return ScreenState.SCOUT, "next_button visible"
    # 5. Attack menu (Find a Match)
    if has("find_match"):
        return ScreenState.ATTACK_MENU, "find_match visible"
    # 6. Own village: Attack! button, or the top-bar builder icon which only
    #    exists on the home village screen (matches even if attack_button
    #    template was captured on a different client theme).
    if has("attack_button"):
        return ScreenState.HOME, "attack_button visible"
    if has("builder_face", 0.80) and has("shield_info", 0.70):
        return ScreenState.HOME, "builder_face+shield landmarks"
    if has("builder_face", 0.90):
        return ScreenState.HOME, "builder_face landmark"
    # 7. Searching clouds: explicit template, or "not home & not loading"
    if has("searching_opponents", 0.75):
        return ScreenState.CLOUDS, "searching_opponents template"
    if looks_like_loading(gray):
        return ScreenState.LOADING, "uniform frame"
    return ScreenState.UNKNOWN, "no landmark matched"
