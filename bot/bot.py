"""Bot: screen IO + full farming state machine (single file, no monkey-patching).

Loop: HOME -> collect/train -> Attack -> Find Match -> [cloud wait -> scout loot
-> Next] -> deploy -> surrender -> Return Home -> repeat, with human-like timing.
"""
from __future__ import annotations
import datetime as dt
import logging
import os
import random
import threading
import time
import cv2
import numpy as np
import yaml

from .adb import AdbDevice
from .vision import Vision
from .upgrade import VillageUpgrader
from .recovery import Recovery
from .army import Army
from .state import ScreenState, classify

log = logging.getLogger("coc")
STATS = {
    "searches": 0,
    "skips": 0,
    "attacks": 0,
    "loot_gold": 0,
    "loot_elixir": 0,
    "loot_dark": 0,
    "buildings_upgraded": 0,
    "lab_researches": 0,
    "walls_upgraded": 0,
    "started": dt.datetime.now(),
}


def load_config(path="config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class Bot:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.W = cfg["screen"]["width"]
        self.H = cfg["screen"]["height"]
        self.adb = AdbDevice(cfg["emulator"].get("adb_serial", ""))
        self.vis = Vision(cfg, self.W, self.H)
        self.upgrader = VillageUpgrader(self)
        self.recovery = Recovery(self)
        self.army = Army(self)
        self.t = cfg["timing"]
        self.f = cfg["farming"]
        self.last_break = time.time()

        # Threading and control states
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._is_running = False
        self._thread: threading.Thread | None = None
        self._adb_lock = threading.Lock()

        # Instance stats
        self.stats = {
            "searches": 0,
            "skips": 0,
            "attacks": 0,
            "loot_gold": 0,
            "loot_elixir": 0,
            "loot_dark": 0,
            "buildings_upgraded": 0,
            "lab_researches": 0,
            "walls_upgraded": 0,
            "started": dt.datetime.now(),
            "current_phase": "Idle",
        }

        # UI callback hooks
        self.on_status: callable[[str], None] | None = None
        self.on_stats: callable[[dict], None] | None = None
        self.on_screen: callable[[np.ndarray, np.ndarray], None] | None = None
        self.on_log: callable[[str, str], None] | None = None

        os.makedirs(cfg.get("vision", {}).get("debug_dir", "logs/last_seen"), exist_ok=True)
        os.makedirs("logs", exist_ok=True)

    # ---------- Thread-safe controls & callbacks ----------
    def set_phase(self, phase: str):
        self.stats["current_phase"] = phase
        log.info("Phase: %s", phase)
        if self.on_status:
            try:
                self.on_status(phase)
            except Exception:
                pass
        self._emit_stats()

    def _emit_stats(self):
        # Mirror to global STATS for compatibility
        for k in ("searches", "skips", "attacks", "loot_gold", "loot_elixir", "loot_dark",
                  "buildings_upgraded", "lab_researches", "walls_upgraded"):
            if k in self.stats:
                STATS[k] = self.stats[k]
        STATS["started"] = self.stats["started"]

        if self.on_stats:
            try:
                self.on_stats(dict(self.stats))
            except Exception:
                pass

    def sleep_interruptible(self, seconds: float, poll: float = 0.1) -> bool:
        """Sleep for `seconds` while responding immediately to pause and stop signals.
        Returns True if the duration elapsed, False if stop was signaled."""
        elapsed = 0.0
        while elapsed < seconds:
            if self._stop_event.is_set():
                return False
            while self._pause_event.is_set():
                if self._stop_event.is_set():
                    return False
                time.sleep(poll)
            step = min(poll, seconds - elapsed)
            time.sleep(step)
            elapsed += step
        return not self._stop_event.is_set()

    def is_running(self) -> bool:
        return self._is_running

    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def start_in_thread(self):
        """Start the bot execution loop in a background daemon thread."""
        if self._is_running:
            if self._pause_event.is_set():
                self.resume()
            return
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._stop_event.clear()
        self._pause_event.clear()
        self._is_running = True
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def pause(self):
        """Pause the bot execution."""
        self._pause_event.set()
        self.set_phase("Paused")

    def resume(self):
        """Resume execution from paused state."""
        self._pause_event.clear()
        self.set_phase("Resumed")

    def stop(self, timeout: float = 2.0):
        """Signal the bot loop to terminate gracefully."""
        self._stop_event.set()
        self._pause_event.clear()
        self.set_phase("Stopped")
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=timeout)
        self._is_running = False

    def reset_stats(self):
        """Reset session counters."""
        self.stats["searches"] = 0
        self.stats["skips"] = 0
        self.stats["attacks"] = 0
        self.stats["loot_gold"] = 0
        self.stats["loot_elixir"] = 0
        self.stats["loot_dark"] = 0
        self.stats["buildings_upgraded"] = 0
        self.stats["lab_researches"] = 0
        self.stats["walls_upgraded"] = 0
        self.stats["started"] = dt.datetime.now()
        self._emit_stats()

    def reload_config(self, cfg: dict):
        """Apply new configuration dynamically without full restart."""
        self.cfg = cfg
        self.W = cfg["screen"]["width"]
        self.H = cfg["screen"]["height"]
        self.t = cfg["timing"]
        self.f = cfg["farming"]
        new_serial = cfg["emulator"].get("adb_serial", "").strip()
        if new_serial != self.adb.serial:
            self.adb = AdbDevice(new_serial)
        self.vis = Vision(cfg, self.W, self.H)
        self.upgrader = VillageUpgrader(self)
        log.info("Configuration reloaded successfully")

    # ---------- IO helpers ----------
    def fx(self, x: float) -> int:
        return int(x * self.W)

    def fy(self, y: float) -> int:
        return int(y * self.H)

    def grab(self):
        """Screenshot via ADB, normalized to configured size. Returns (bgr, gray)."""
        with self._adb_lock:
            png = self.adb.screencap()
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Failed to decode screencap image")
        img = cv2.resize(img, (self.W, self.H))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if self.cfg.get("vision", {}).get("debug_save"):
            cv2.imwrite(os.path.join(self.cfg["vision"]["debug_dir"], "screen.png"), img)
        if self.on_screen:
            try:
                self.on_screen(img, gray)
            except Exception:
                pass
        return img, gray

    def tap_frac(self, x: float, y: float):
        if self._stop_event.is_set():
            return
        with self._adb_lock:
            self.adb.tap(self.fx(x), self.fy(y), self.t.get("jitter_px", 4))
        delay = random.uniform(self.t["min_tap_delay"], self.t["max_tap_delay"])
        self.sleep_interruptible(delay)

    def adb_tap(self, x: int, y: int):
        """Raw pixel tap with jitter + human pacing, stop-aware."""
        if self._stop_event.is_set():
            return
        with self._adb_lock:
            self.adb.tap(x, y, self.t.get("jitter_px", 4))
        delay = random.uniform(self.t["min_tap_delay"], self.t["max_tap_delay"])
        self.sleep_interruptible(delay)

    def adb_shell(self, command: str) -> str:
        """Thread-safe raw adb shell (used by recovery: force-stop, keyevent...)."""
        with self._adb_lock:
            try:
                return self.adb.shell(command)
            except Exception as e:
                log.debug("adb shell failed: %s", e)
                return ""

    def adb_keyevent(self, code: int):
        """Thread-safe Android keyevent (4=BACK, 3=HOME)."""
        with self._adb_lock:
            try:
                self.adb.keyevent(code)
            except Exception as e:
                log.debug("adb keyevent failed: %s", e)

    def current_state(self) -> tuple[ScreenState, str]:
        """Grab a frame and classify it. Returns (ScreenState, reason)."""
        img, gray = self.grab()
        return classify(img, gray, self.vis, self.cfg)

    def tap_match(self, gray, name: str, thresh=None) -> bool:
        if self._stop_event.is_set():
            return False
        m = self.vis.find(gray, name, thresh)
        if m:
            cx, cy, s = m
            log.debug("found %s (%.2f) @ %d,%d", name, s, cx, cy)
            with self._adb_lock:
                self.adb.tap(cx, cy, self.t.get("jitter_px", 4))
            delay = random.uniform(self.t["min_tap_delay"], self.t["max_tap_delay"])
            self.sleep_interruptible(delay)
            return True
        return False

    def wait_for(self, name: str, timeout: float = 20.0, poll: float = 0.7):
        """Poll screenshots until template `name` appears. Returns (cx, cy) or None."""
        t0, last_log = time.time(), 0.0
        while time.time() - t0 < timeout:
            if self._stop_event.is_set():
                return None
            try:
                _, gray = self.grab()
                m = self.vis.find(gray, name)
                if m:
                    return (m[0], m[1])
            except Exception as e:
                log.debug("wait_for screencap error: %s", e)
            if time.time() - last_log > 10:
                log.info("waiting for %s... (%.0fs/%.0fs)", name, time.time() - t0, timeout)
                last_log = time.time()
            if not self.sleep_interruptible(poll):
                return None
        log.warning("timeout waiting for %s", name)
        return None

    def _brightness_at(self, gray, x: float, y: float, w: float = 0.045, h: float = 0.06) -> float:
        """Mean brightness of a small region (used for troop-slot highlight checks)."""
        crop = gray[self.fy(y - h / 2):self.fy(y + h / 2),
                    self.fx(x - w / 2):self.fx(x + w / 2)]
        return float(crop.mean()) if crop.size else -1.0

    # ---------- phases ----------
    def collect_and_train(self):
        if self._stop_event.is_set():
            return
        self.set_phase("Collecting Resources")
        self.recovery.handle_connection_lost()
        _, gray = self.grab()
        if self.f.get("collect_resources"):
            # Actively search for and tap gold and elixir collector bubbles
            for bubble_template in ("collect_gold", "collect_elixir"):
                for _ in range(6):
                    if self._stop_event.is_set():
                        return
                    if not self.tap_match(gray, bubble_template, thresh=0.72):
                        break
                    self.sleep_interruptible(0.6)
                    _, gray = self.grab()

            # Sweep base coordinates in case bubbles are partially obscured
            for cx, cy in [(0.35, 0.45), (0.65, 0.45), (0.50, 0.35), (0.50, 0.55), (0.30, 0.55), (0.70, 0.35)]:
                if self._stop_event.is_set():
                    return
                self.tap_frac(cx, cy)
                self.sleep_interruptible(0.3)

        # Run Village Auto-Upgrade Engine (buildings, heroes, lab, walls)
        if self.upgrader.is_enabled():
            self.upgrader.run_upgrade_cycle()
            if self._stop_event.is_set():
                return

        self.set_phase("Training Troops")
        if self.f.get("train_army"):
            _, gray = self.grab()
            if self.tap_match(gray, "train_button"):
                self.sleep_interruptible(1.5)
                if self._stop_event.is_set():
                    return
                _, gray = self.grab()
                self.tap_match(gray, "quick_train")
                self.sleep_interruptible(1.0)
                _, gray = self.grab()
                if not self.tap_match(gray, "close_modal"):
                    self.tap_frac(0.05, 0.30)
                self.sleep_interruptible(1.0)

    def upgrade_village_now(self) -> dict:
        """Trigger an immediate village upgrade cycle on demand."""
        return self.upgrader.run_upgrade_cycle()

    def _storages_full(self) -> bool:
        """True when gold AND elixir bars read as full (>= full_ratio).
        Only trusted on the HOME screen (bars don't exist elsewhere).
        Unreadable bars (-1) count as NOT full so we never stall on bad reads."""
        try:
            img, gray = self.grab()
            state, _ = classify(img, gray, self.vis, self.cfg)
            if state is not ScreenState.HOME:
                log.debug("storage check skipped: not on home (%s)", state.value)
                return False
            fill = self.vis.read_storage_fill(img)
        except Exception as e:
            log.debug("storage fill check failed: %s", e)
            return False
        ratio = float(self.f.get("full_ratio", 0.97))
        g, e = fill.get("gold", -1.0), fill.get("elixir", -1.0)
        log.info("storage fill: gold=%.1f%% elixir=%.1f%% dark=%.1f%%",
                 g * 100, e * 100, fill.get("dark", -1.0) * 100)
        return 0 <= g >= ratio and 0 <= e >= ratio

    def start_search(self) -> bool:
        """Open Attack -> Find Match, then ride out matchmaking clouds."""
        if self._stop_event.is_set():
            return False
        self.set_phase("Starting Search")
        _, gray = self.grab()
        if self.f.get('check_shield'):
            if self.vis.find(gray, 'shield_info'):
                log.info('Shield is active, skipping attack')
                return False
        if not self.tap_match(gray, "attack_button"):
            log.warning("attack_button not found — is village loaded?")
            return False
        if not self.sleep_interruptible(2.0):
            return False
        _, gray = self.grab()
        if not self.tap_match(gray, "find_match"):
            log.warning("find_match not found")
            return False
        # Clouds: state-aware wait (handles disconnects, kicked-home, timeouts).
        return self.wait_for_scout(timeout=60.0)

    def wait_for_scout(self, timeout: float = 60.0) -> bool:
        """Ride out matchmaking clouds until an enemy village is shown.
        Handles: reload dialogs mid-search, being kicked back home,
        instant matches, and timeouts. Returns True when scouting/battle."""
        self.set_phase("Matchmaking Clouds")
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self._stop_event.is_set():
                return False
            try:
                img, gray = self.grab()
            except Exception as e:
                log.debug("grab failed in cloud wait: %s", e)
                self.sleep_interruptible(2.0)
                continue
            state, reason = classify(img, gray, self.vis, self.cfg)
            log.debug("cloud wait: %s (%s)", state.value, reason)
            if state in (ScreenState.SCOUT, ScreenState.BATTLE):
                return True
            if state is ScreenState.RELOAD_DIALOG:
                self.recovery.handle_connection_lost()
                try:
                    img2, gray2 = self.grab()
                    st2, _ = classify(img2, gray2, self.vis, self.cfg)
                except Exception:
                    continue
                if st2 is ScreenState.ATTACK_MENU:
                    self.tap_match(gray2, "find_match")
                elif st2 is ScreenState.HOME:
                    return False
                continue
            if state is ScreenState.HOME:
                log.warning("kicked back home during matchmaking — aborting search")
                return False
            self.sleep_interruptible(1.0)
        log.warning("cloud wait timeout (%.0fs)", timeout)
        return False

    def evaluate_village(self, img):
        loot = self.vis.read_loot(img)
        g, e, d = loot["gold"], loot["elixir"], loot["dark"]
        log.info("loot scout: gold=%s elixir=%s dark=%s", g, e, d)
        if g < 0 and e < 0:
            log.warning("loot unread (calibrate loot_boxes / digits) — pressing Next")
            return False, loot

        min_g = self.f.get("min_gold", 0)
        min_e = self.f.get("min_elixir", 0)
        min_d = self.f.get("min_dark", 0)

        gold_ok = (min_g <= 0) or (g >= min_g)
        elixir_ok = (min_e <= 0) or (e >= min_e)
        # If min_dark is <= 0 (ignore DE), do not reject when dark is unread (-1)
        dark_ok = (min_d <= 0) or (d >= min_d)

        ok = gold_ok and elixir_ok and dark_ok
        return ok, loot

    def select_troop(self, xs, idx: int, baseline: float) -> int:
        """Tap troop slot `idx`; verify it highlighted. Returns index actually
        selected (falls back to next slots), or -1 if none responded."""
        by = self.f["troops"]["troop_bar_y"]
        for k in range(len(xs)):
            if self._stop_event.is_set():
                return -1
            i = (idx + k) % len(xs)
            self.tap_frac(xs[i], by)
            _, gray = self.grab()
            if self._brightness_at(gray, xs[i], by) > baseline + 6:
                return i
            log.debug("troop slot %d looked empty/unresponsive", i)
        return -1

    def attack(self):
        if self._stop_event.is_set():
            return
        self.set_phase("Deploying Troops")
        pts = self.f["deploy_points"]
        xs = self.f["troops"]["barracks_slots"]
        by = self.f["troops"]["troop_bar_y"]
        drops = self.f["troops"]["drops_per_point"]
        iv = self.f["troops"]["drop_interval_sec"]

        # Primary: dynamic troop-bar scan + swipe-hold wave deploy.
        deployed = False
        try:
            deployed = self.army.deploy()
        except Exception as e:
            log.warning("dynamic deploy failed (%s) — legacy fallback", e)

        # Fallback: legacy fixed-slot deploy (verified selection via brightness).
        if not deployed and not self._stop_event.is_set():
            _, gray = self.grab()
            ti = self.select_troop(xs, 0, self._brightness_at(gray, xs[0], by))
            if ti < 0:
                log.warning("no troop slot responded — aborting attack")
            else:
                for (px, py) in pts:
                    if self._stop_event.is_set():
                        return
                    for _ in range(drops):
                        if self._stop_event.is_set():
                            return
                        self.tap_frac(px, py)
                        self.sleep_interruptible(random.uniform(iv[0], iv[1]))
                    nxt = self.select_troop(xs, ti + 1, self._brightness_at(gray, xs[ti], by))
                    ti = nxt if nxt >= 0 else ti

        # Wait out the battle, but bail early the moment it actually ends.
        surrender_wait = self.f["surrender_after_sec"]
        self.set_phase(f"In Battle (max {surrender_wait}s)")
        log.info("deployed, watching battle (max %ss)", surrender_wait)
        t0 = time.time()
        while time.time() - t0 < surrender_wait:
            if not self.sleep_interruptible(3.0):
                return
            try:
                img, gray = self.grab()
                state, _ = classify(img, gray, self.vis, self.cfg)
            except Exception:
                continue
            if state in (ScreenState.BATTLE_END, ScreenState.HOME):
                log.info("battle ended early (%.0fs)", time.time() - t0)
                break
            if state is ScreenState.RELOAD_DIALOG:
                self.recovery.handle_connection_lost()
                break
        self.end_battle()

    def end_battle(self):
        """Surrender -> confirm -> Return Home, fully state-driven.

        Covers: battle already over, surrender hidden, confirm dialog lag,
        banners covering Return Home, disconnects mid-exit. Returns only when
        home is confirmed or the 45s bound is hit (recovery handles the rest).
        """
        if self._stop_event.is_set():
            return
        self.set_phase("Ending Battle")

        # 1. Surrender if the fight is still running
        try:
            img, gray = self.grab()
            state, _ = classify(img, gray, self.vis, self.cfg)
        except Exception:
            state, gray = ScreenState.UNKNOWN, None
        if state is ScreenState.BATTLE and gray is not None:
            m = self.vis.find(gray, "surrender_button")
            if m:
                self.adb_tap(m[0], m[1])
                self.sleep_interruptible(1.2)
                c = self.wait_for("confirm_surrender", timeout=8)
                if c:
                    self.adb_tap(c[0], c[1])
        else:
            log.info("battle already ended on its own (%s)", state.value)

        # 2. Get home: prefer Return Home template, blind fallback after 12s,
        #    handle disconnects, finish the instant HOME is confirmed.
        fb = self.f.get("return_home_fallback", [0.5, 0.92])
        t0 = time.time()
        while time.time() - t0 < 45:
            if self._stop_event.is_set():
                return
            try:
                img, gray = self.grab()
            except Exception:
                self.sleep_interruptible(2.0)
                continue
            state, _ = classify(img, gray, self.vis, self.cfg)
            if state is ScreenState.HOME:
                self.sleep_interruptible(1.0)
                return
            if state is ScreenState.RELOAD_DIALOG:
                self.recovery.handle_connection_lost()
                continue
            if state is ScreenState.LOADING:
                self.sleep_interruptible(2.0)
                continue
            m = self.vis.find(gray, "return_home")
            if m:
                self.adb_tap(m[0], m[1])
                self.sleep_interruptible(3.0)
                continue
            if time.time() - t0 > 12:
                log.info("return_home not found, tapping fallback %s", fb)
                self.tap_frac(fb[0], fb[1])
                self.sleep_interruptible(2.5)
        log.warning("end_battle: home not confirmed within 45s — recovery will handle it")

    def maybe_long_break(self):
        if self._stop_event.is_set():
            return
        if time.time() - self.last_break > self.t["long_break_every_min"] * 60:
            s = random.uniform(*self.t["long_break_sec"])
            self.set_phase(f"Anti-Ban Break ({int(s)}s)")
            log.info("anti-ban long break %.0fs", s)
            self.sleep_interruptible(s)
            self.last_break = time.time()

    # ---------- main loop ----------
    def run(self):
        self._is_running = True
        self._stop_event.clear()
        self.set_phase("Connecting ADB")
        if not self.adb.ensure_connected():
            log.error("No ADB device. Connect emulator: `adb connect 127.0.0.1:5555` then retry.")
            log.error("BlueStacks: Settings > Advanced > ADB. LDPlayer: Settings > Advanced > ADB debugging.")
            self.set_phase("ADB Error")
            self._is_running = False
            return

        log.info("connected: %s", self.adb.serial or "(default)")
        log.info("targets: gold>=%s elixir>=%s dark>=%s",
                 self.f["min_gold"], self.f["min_elixir"], self.f.get("min_dark", 0))

        # Check for missing templates and warn clearly
        missing = self.vis.missing_templates()
        if missing:
            log.warning("Notice: Missing templates: %s. Please capture them in the UI template studio.",
                        ", ".join(missing))

        try:
            while not self._stop_event.is_set():
                self.maybe_long_break()
                if self._stop_event.is_set():
                    break
                # Gatekeeper: never run a cycle from an unknown screen.
                self.set_phase("Ensuring Home Screen")
                if not self.recovery.ensure_home():
                    log.warning("could not reach home screen — retrying in 20s")
                    self.sleep_interruptible(20.0)
                    continue
                self.recovery.clear_popups()
                if self._stop_event.is_set():
                    break
                self.collect_and_train()
                if self._stop_event.is_set():
                    break
                # Skip pointless farming when storages are already full.
                if self.f.get("skip_attack_when_full", True) and self._storages_full():
                    self.set_phase("Storage Full — Idling")
                    self.sleep_interruptible(random.uniform(120, 240))
                    self.last_break = time.time()
                    continue
                if not self.start_search():
                    self.sleep_interruptible(10.0)
                    continue
                if self._stop_event.is_set():
                    break
                self.search_loop()
        except KeyboardInterrupt:
            log.info("stopped after %.0f min | %s",
                     (dt.datetime.now() - self.stats["started"]).total_seconds() / 60, self.stats)
        except Exception as e:
            log.exception("loop error: %s", e)
        finally:
            self._is_running = False
            self.set_phase("Idle")

    def search_loop(self):
        """Scout villages until a good one is found, max_searches cap."""
        for search_idx in range(1, self.f["max_searches"] + 1):
            if self._stop_event.is_set():
                return
            pause = random.uniform(*self.t["search_pause_sec"])
            if not self.sleep_interruptible(pause):
                return

            self.set_phase(f"Scouting Base ({search_idx}/{self.f['max_searches']})")
            try:
                img, gray = self.grab()
            except Exception as e:
                log.warning("Screen grab failed during search: %s", e)
                return

            self.stats["searches"] += 1
            self._emit_stats()

            # state guards: never evaluate loot on the wrong screen
            state, _reason = classify(img, gray, self.vis, self.cfg)
            if state is ScreenState.RELOAD_DIALOG:
                log.warning("disconnect during search — handling and aborting")
                self.recovery.handle_connection_lost()
                return
            if state is ScreenState.HOME:
                log.warning("kicked home mid-search — aborting")
                return

            # battle might have started by itself (defense / lag)
            if self.vis.find(gray, "surrender_button"):
                log.warning("battle started unexpectedly — fighting it out")
                self.sleep_interruptible(self.f["surrender_after_sec"])
                self.end_battle()
                return

            good, loot = self.evaluate_village(img)
            if good:
                self.stats["attacks"] += 1
                self._emit_stats()
                log.info("ATTACK #%d | searched=%d skipped=%d | session loot G:%d E:%d DE:%d",
                         self.stats["attacks"], self.stats["searches"], self.stats["skips"],
                         self.stats["loot_gold"], self.stats["loot_elixir"], self.stats["loot_dark"])
                self.attack()
                self.stats["loot_gold"] += max(loot["gold"], 0)
                self.stats["loot_elixir"] += max(loot["elixir"], 0)
                self.stats["loot_dark"] += max(loot.get("dark", 0), 0)
                self._emit_stats()
                after_wait = random.uniform(*self.t["after_attack_pause_sec"])
                self.sleep_interruptible(after_wait)
                return

            self.stats["skips"] += 1
            self._emit_stats()
            if not self.tap_match(gray, "next_button"):
                log.warning("next_button missing — restarting search")
                return
            if not self.wait_for_scout(timeout=30):
                log.warning("no next village (clouds/disconnect) — restarting search")
                return
        else:
            self.set_phase("Max Searches Cooldown")
            log.info("max searches hit, cooling down 60s")
            self.tap_frac(0.05, 0.03)
            self.sleep_interruptible(2.0)
            self.sleep_interruptible(60.0)
            self.last_break = time.time()
