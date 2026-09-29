"""Village Auto-Upgrade Engine for Clash of Clans.

Handles:
1. Builder Menu & Suggested Upgrades:
   - Checks if builders are free or busy.
   - Taps suggested upgrades list, reviews resource requirements, and executes upgrades.
   - Strictly rejects gem-purchase dialogs when resources are insufficient.
2. Laboratory Research:
   - Checks if Laboratory is active/busy.
   - Triggers troop or spell research when lab is idle.
3. Wall Upgrades (Resource Sink):
   - Dumps excess Gold and Elixir into walls to prevent resource overflow.
"""
from __future__ import annotations
import logging
import random
import time
from typing import TYPE_CHECKING
import cv2

if TYPE_CHECKING:
    from bot.bot import Bot

log = logging.getLogger("coc.upgrade")


class VillageUpgrader:
    def __init__(self, bot: Bot):
        self.bot = bot

    @property
    def cfg(self) -> dict:
        return self.bot.cfg.get("upgrades", {})

    def is_enabled(self) -> bool:
        return bool(self.cfg.get("enabled", True))

    # ---------- speed helpers ----------
    def _settle(self, lo: float = 0.3, hi: float = 0.7):
        """Short human-paced pause between verified steps.
        fast_mode=true (default) keeps it snappy; false = legacy slow pacing."""
        if self.cfg.get("fast_mode", True):
            self.bot.sleep_interruptible(lo, hi)
        else:
            self.bot.sleep_interruptible(max(lo, 1.2), max(hi, 1.8))

    def _wait_any(self, keys, timeout: float = 3.0, step: float = 0.35,
                  thresh: float = 0.70):
        """Poll the screen until ANY of `keys` matches. Returns (key, match)
        or (None, None) on timeout. Replaces blind fixed sleeps: faster AND
        more reliable because we act the instant the UI responds."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.bot._stop_event.is_set():
                return None, None
            try:
                _, gray = self.bot.grab()
            except Exception:
                self.bot.sleep_interruptible(step)
                continue
            for k in keys:
                m = self.bot.vis.find(gray, k, thresh=thresh)
                if m:
                    return k, m
            self.bot.sleep_interruptible(step)
        return None, None

    def close_modal(self):
        """Dismiss open dialogs or return to home village screen."""
        if self.bot._stop_event.is_set():
            return
        _, gray = self.bot.grab()
        if self.bot.tap_match(gray, "close_modal", thresh=0.70):
            self._settle()
            return
        # 1. Try shop close button at top right (1230, 75 in 1280x720)
        self.bot.tap_frac(0.96, 0.10)
        self._settle(0.25, 0.45)
        # 2. Try modal confirmation dialog close button (1130, 65)
        close_frac = self.cfg.get("close_modal_frac", [0.88, 0.09])
        self.bot.tap_frac(close_frac[0], close_frac[1])
        self._settle(0.25, 0.45)
        # 3. Tap empty grass (640, 200) to clear any active building selection
        self.bot.tap_frac(0.50, 0.28)
        self._settle()

    def get_free_builders(self, gray) -> int:
        """Detect exact number of free builders (0, 1, 2) from top bar HUD.
        Returns -1 if undetermined."""
        if gray is None:
            return -1
        # Search specifically in top bar builder HUD: y=20..70, x=580..700
        h, w = gray.shape[:2]
        if h >= 70 and w >= 700:
            hud = gray[20:70, 580:700]
            scores = {}
            for n, key in [(0, "zero_builders"), (1, "one_builder"), (2, "two_builders")]:
                tpl = self.bot.vis.templates.get(key)
                if tpl is not None and tpl.shape[0] <= hud.shape[0] and tpl.shape[1] <= hud.shape[1]:
                    res = cv2.matchTemplate(hud, tpl, cv2.TM_CCOEFF_NORMED)
                    _, max_v, _, _ = cv2.minMaxLoc(res)
                    scores[n] = max_v
            if scores:
                best_n = max(scores, key=scores.get)
                if scores[best_n] >= 0.82:
                    return best_n

        # Fallback full screen checks
        if self.bot.vis.find(gray, "all_builders_busy", thresh=0.75):
            return 0
        if self.bot.vis.find(gray, "zero_builders", thresh=0.85):
            return 0
        return -1

    def check_builders_busy(self, gray) -> bool:
        """Return True if builders are confirmed to be busy (0 free)."""
        if gray is None:
            return False
        free = self.get_free_builders(gray)
        if free == 0:
            return True
        if self.bot.vis.find(gray, "all_builders_busy", thresh=0.75):
            return True
        if self.bot.vis.find(gray, "zero_builders", thresh=0.85):
            return True
        return False

    def is_gem_prompt_active(self, gray, img=None) -> bool:
        """Return True if any gem purchase prompt or Finish Now button is present.
        Strictly protects player gems from being spent."""
        if gray is None:
            return False

        # 1. Dialog header 'All builders are busy!'
        if self.bot.vis.find(gray, "all_builders_busy", thresh=0.70):
            log.warning("Anti-Gem Protection: 'all_builders_busy' modal detected!")
            return True

        # 2. 'Finish Now' button with gem icon (common in upgrade dialogs and dock)
        if self.bot.vis.find(gray, "finish_now", thresh=0.75):
            log.warning("Anti-Gem Protection: 'finish_now' gem button detected!")
            return True

        # 3. Gem crystal icon inside the modal / action region (excluding HUD at top right)
        # Action region: y=160..680, x=200..1050
        h, w = gray.shape[:2]
        if h >= 680 and w >= 1050:
            action_gray = gray[160:680, 200:1050]
            gem_tpl = self.bot.vis.templates.get("gem_icon")
            if gem_tpl is not None and gem_tpl.shape[0] <= action_gray.shape[0] and gem_tpl.shape[1] <= action_gray.shape[1]:
                res = cv2.matchTemplate(action_gray, gem_tpl, cv2.TM_CCOEFF_NORMED)
                _, max_v, _, max_loc = cv2.minMaxLoc(res)
                if max_v >= 0.75:
                    log.warning("Anti-Gem Protection: 'gem_icon' detected in action area (score=%.2f at %s)!", max_v, max_loc)
                    return True

        return False


    def open_builder_menu(self) -> bool:
        """Tap builder icon in top bar to open Suggested Upgrades dropdown."""
        if self.bot._stop_event.is_set():
            return False
        _, gray = self.bot.grab()
        if not self.bot.tap_match(gray, "builder_face", thresh=0.70):
            # Fallback to fractional coord (600, 45 in 1280x720)
            head_pos = self.cfg.get("builder_head_frac", [0.468, 0.062])
            self.bot.tap_frac(head_pos[0], head_pos[1])

        # Verified wait: menu open, or builders-busy panel, or give up.
        key, _ = self._wait_any(["suggested_upgrades", "all_builders_busy",
                                 "zero_builders"], timeout=4.0)
        return key is not None

    def upgrade_building_at_coords(self, x: int, y: int, name: str = "building") -> bool:
        """Attempt to select and upgrade a village building at pixel coordinates (x, y)."""
        if self.bot._stop_event.is_set():
            return False

        # Pre-check: Don't tap buildings if builders are confirmed busy
        _, gray = self.bot.grab()
        if self.check_builders_busy(gray):
            log.info("Builders are busy (0 free). Cannot upgrade '%s'.", name)
            return False

        # Deselect any previous selection first
        self.bot.tap_frac(0.50, 0.28)
        self._settle(0.3, 0.5)

        # Tap target building, then VERIFIED wait for the action dock
        log.info("Inspecting building '%s' at (%d, %d)", name, x, y)
        self.bot.adb.tap(x, y, self.bot.t.get("jitter_px", 4))
        key, match = self._wait_any(["upgrade_button", "finish_now"],
                                    timeout=2.5, thresh=0.70)
        if key == "finish_now":
            log.info("Building '%s' already upgrading (Finish Now). Skipping.", name)
            self.bot.tap_frac(0.50, 0.28)
            return False
        if key != "upgrade_button":
            log.debug("No active upgrade button for '%s'", name)
            self.bot.tap_frac(0.50, 0.28)
            return False

        # Safety: gem prompt may be up instead of a normal dock
        img, gray = self.bot.grab()
        if self.is_gem_prompt_active(gray, img):
            log.info("Building '%s' gem prompt active. Skipping.", name)
            self.bot.tap_frac(0.50, 0.28)
            return False

        ux, uy, _ = match
        log.info("Tapping upgrade button for '%s' at (%d, %d)", name, ux, uy)
        self.bot.adb.tap(ux, uy, self.bot.t.get("jitter_px", 4))

        # Verified wait for the confirmation dialog (or gem prompt)
        confirm_keys = ["confirm_upgrade_gold", "confirm_upgrade_elixir",
                        "confirm_upgrade_de"]
        if self.cfg.get("upgrade_heroes", True):
            confirm_keys.append("confirm_upgrade_hero")

        t0 = time.time()
        while time.time() - t0 < 3.5:
            if self.bot._stop_event.is_set():
                return False
            img, gray = self.bot.grab()
            if self.is_gem_prompt_active(gray, img):
                log.warning("CRITICAL Anti-Gem: Gem purchase prompted for '%s'! Rejecting.", name)
                self.close_modal()
                return False
            hit = None
            for ck in confirm_keys:
                hit = self.bot.vis.find(gray, ck, thresh=0.70)
                if hit:
                    break
            if hit:
                break
            self.bot.sleep_interruptible(0.35)
        else:
            hit = None

        if not hit:
            log.info("No valid resource confirmation for '%s'. Cancelling.", name)
            self.close_modal()
            return False

        # Reserve check (single read on the same dialog frame)
        loot = self.bot.vis.read_loot(img)
        r_g = int(self.cfg.get("reserve_gold", 0))
        r_e = int(self.cfg.get("reserve_elixir", 0))
        if loot:
            g, e = loot.get("gold", -1), loot.get("elixir", -1)
            if (g != -1 and g < r_g) or (e != -1 and e < r_e):
                log.warning("Resources below reserves (%s: g=%d, e=%d). Aborting.", name, g, e)
                self.close_modal()
                return False

        self.bot.adb.tap(hit[0], hit[1], self.bot.t.get("jitter_px", 4))
        self.bot.stats["buildings_upgraded"] = self.bot.stats.get("buildings_upgraded", 0) + 1
        self.bot._emit_stats()
        log.info("Successfully started upgrade for '%s'!", name)
        self._settle(0.8, 1.4)
        self.bot.tap_frac(0.50, 0.28)
        return True

    def upgrade_village_buildings(self) -> int:
        """Scan and upgrade standard village buildings directly on the map.
        Guarantees progression from scratch on early TH levels (TH2/TH3)."""
        if not self.cfg.get("upgrade_buildings", True):
            return 0

        # Core building coordinates for 1280x720 layout
        BUILDING_TARGETS = [
            ("Barracks", 640, 380),
            ("Gold Storage", 580, 330),
            ("Elixir Storage", 510, 340),
            ("Gold Mine", 490, 275),
            ("Elixir Collector", 365, 425),
            ("Cannon", 325, 335),
            ("Army Camp", 530, 450),
            ("Town Hall", 440, 360),
        ]

        upgraded = 0
        max_upgrades = int(self.cfg.get("max_upgrades_per_cycle", 3))

        for name, bx, by in BUILDING_TARGETS:
            if self.bot._stop_event.is_set() or upgraded >= max_upgrades:
                break

            _, gray = self.bot.grab()
            if self.check_builders_busy(gray):
                log.info("All builders busy during village scan. Stopping.")
                break

            self.bot.set_phase(f"Village Upgrade: {name}")
            if self.upgrade_building_at_coords(bx, by, name=name):
                upgraded += 1

        return upgraded

    def upgrade_suggested_buildings(self) -> int:
        """Inspect and upgrade buildings from the Suggested Upgrades menu."""
        if not self.cfg.get("upgrade_buildings", True):
            return 0

        upgraded = 0
        max_upgrades = int(self.cfg.get("max_upgrades_per_cycle", 3))

        for attempt in range(max_upgrades):
            if self.bot._stop_event.is_set():
                break

            self.bot.set_phase(f"Checking Upgrades ({attempt + 1}/{max_upgrades})")
            if not self.open_builder_menu():
                log.debug("Could not open builder menu, skipping")
                break

            _, gray = self.bot.grab()
            if self.check_builders_busy(gray):
                log.info("All builders are busy. Skipping building upgrades.")
                self.close_modal()
                break

            # Find Suggested Upgrades header
            header = self.bot.vis.find(gray, "suggested_upgrades", thresh=0.68)
            if not header:
                log.info("No suggested upgrades available")
                self.close_modal()
                break

            hx, hy, _ = header
            # Row spacing in dropdown (hy ~ 162, row 1 ~ 217, row 2 ~ 272, etc.)
            item_y = hy + 55 + (attempt * 55)
            log.info("Inspecting suggested upgrade row #%d at (%d, %d)", attempt + 1, hx, item_y)
            self.bot.adb.tap(hx, item_y, self.bot.t.get("jitter_px", 4))

            # Verified wait: dock (upgrade button) or busy/gem panel appears
            key, upgrade_match = self._wait_any(
                ["upgrade_button", "all_builders_busy", "zero_builders", "finish_now"],
                timeout=2.5, thresh=0.70)
            img, gray = self.bot.grab()
            if key in ("all_builders_busy", "zero_builders", "finish_now") \
                    or self.is_gem_prompt_active(gray, img):
                log.info("All builders busy or gem finish prompted after item selection")
                self.close_modal()
                break
            if key != "upgrade_button":
                log.info("Upgrade button not active or shop opened. Dismissing.")
                self.close_modal()
                continue

            ux, uy, _ = upgrade_match
            log.info("Tapping upgrade action button at (%d, %d)", ux, uy)
            self.bot.adb.tap(ux, uy, self.bot.t.get("jitter_px", 4))

            # Verified wait for confirm dialog; Anti-Gem checked on every poll
            confirm_keys = ["confirm_upgrade_gold", "confirm_upgrade_elixir",
                            "confirm_upgrade_de"]
            if self.cfg.get("upgrade_heroes", True):
                confirm_keys.append("confirm_upgrade_hero")

            hit = None
            img = gray = None
            t0 = time.time()
            while time.time() - t0 < 3.5:
                if self.bot._stop_event.is_set():
                    return upgraded
                img, gray = self.bot.grab()
                if self.is_gem_prompt_active(gray, img):
                    log.warning("CRITICAL Anti-Gem: Gem purchase prompted in suggested upgrade! Cancelling.")
                    self.close_modal()
                    return upgraded
                for ck in confirm_keys:
                    hit = self.bot.vis.find(gray, ck, thresh=0.70)
                    if hit:
                        break
                if hit:
                    break
                self.bot.sleep_interruptible(0.35)

            if not hit:
                log.warning("Valid resource confirmation not found. Cancelling.")
                self.close_modal()
                break

            loot = self.bot.vis.read_loot(img)
            r_g = int(self.cfg.get("reserve_gold", 0))
            r_e = int(self.cfg.get("reserve_elixir", 0))
            if loot:
                g, e = loot.get("gold", -1), loot.get("elixir", -1)
                if (g != -1 and g < r_g) or (e != -1 and e < r_e):
                    log.warning("Resources below reserves. Aborting upgrade.")
                    self.close_modal()
                    continue

            self.bot.adb.tap(hit[0], hit[1], self.bot.t.get("jitter_px", 4))
            upgraded += 1
            self.bot.stats["buildings_upgraded"] = self.bot.stats.get("buildings_upgraded", 0) + 1
            self.bot._emit_stats()
            log.info("Successfully started building upgrade #%d!", upgraded)
            self._settle(0.8, 1.4)

        return upgraded

    def upgrade_laboratory(self) -> int:
        """Inspect and start laboratory research if laboratory is free."""
        if not self.cfg.get("upgrade_lab", True):
            return 0

        self.bot.set_phase("Checking Laboratory")
        lab_pos = self.cfg.get("lab_icon_frac", [0.36, 0.035])
        self.bot.tap_frac(lab_pos[0], lab_pos[1])

        # Verified wait for the lab panel (busy banner or research grid)
        self._wait_any(["lab_busy", "btn_lab_confirm", "btn_lab_confirm_de"],
                       timeout=3.0, thresh=0.75)
        _, gray = self.bot.grab()
        if self.bot.vis.find(gray, "lab_busy", thresh=0.75):
            log.info("Laboratory research is currently active.")
            self.close_modal()
            return 0

        researched = 0
        for pos in [[0.25, 0.45], [0.40, 0.45]]:
            self.bot.tap_frac(pos[0], pos[1])
            self._settle(0.5, 0.9)
            img, gray = self.bot.grab()
            
            # Anti-Gem check before lab confirm
            if self.is_gem_prompt_active(gray, img):
                log.warning("Anti-Gem: Gem prompt active during lab research check. Aborting.")
                break

            confirmed = False
            for key in ("btn_lab_confirm", "btn_lab_confirm_de"):
                if self.bot.tap_match(gray, key, thresh=0.75):
                    log.info("Started Laboratory research using %s!", key)
                    researched = 1
                    self.bot.stats["lab_researches"] = self.bot.stats.get("lab_researches", 0) + 1
                    self.bot._emit_stats()
                    self.bot.sleep_interruptible(1.5)
                    confirmed = True
                    break
                    
            if confirmed:
                break
                
        self.close_modal()
        return researched

    def upgrade_walls(self) -> int:
        """Dump excess gold/elixir into walls if resources exceed configured triggers."""
        if not self.cfg.get("upgrade_walls", True):
            return 0

        try:
            img, gray = self.bot.grab()
            loot = self.bot.vis.read_loot(img)
            if not loot:
                return 0
                
            g, e = loot.get("gold", -1), loot.get("elixir", -1)
            g_trig = int(self.cfg.get("wall_gold_trigger", 4000000))
            e_trig = int(self.cfg.get("wall_elixir_trigger", 4000000))
            
            if (g != -1 and g > g_trig) or (e != -1 and e > e_trig):
                log.info("Resources exceed wall triggers. Attempting wall upgrade.")
                wall_tap = self.cfg.get("wall_tap_frac", [0.50, 0.50])
                self.bot.tap_frac(wall_tap[0], wall_tap[1])

                # Verified wait for the wall's action dock
                key, upgrade_match = self._wait_any(["upgrade_button", "finish_now"],
                                                    timeout=2.5, thresh=0.72)
                img, gray = self.bot.grab()
                if self.is_gem_prompt_active(gray, img):
                    log.warning("Anti-Gem: Gem prompt on wall tap. Dismissing.")
                    self.close_modal()
                    return 0
                if key != "upgrade_button" or not upgrade_match:
                    self.close_modal()
                    return 0

                ux, uy, _ = upgrade_match
                self.bot.adb.tap(ux, uy, self.bot.t.get("jitter_px", 4))

                # Verified wait for the confirm dialog (Anti-Gem every poll)
                hit = None
                t0 = time.time()
                while time.time() - t0 < 3.0:
                    if self.bot._stop_event.is_set():
                        return 0
                    img, gray = self.bot.grab()
                    if self.is_gem_prompt_active(gray, img):
                        log.warning("Anti-Gem: Gem prompt on wall upgrade confirm. Dismissing.")
                        self.close_modal()
                        return 0
                    for ck in ("confirm_upgrade_gold", "confirm_upgrade_elixir"):
                        hit = self.bot.vis.find(gray, ck, thresh=0.75)
                        if hit:
                            break
                    if hit:
                        break
                    self.bot.sleep_interruptible(0.35)

                if hit:
                    self.bot.adb.tap(hit[0], hit[1], self.bot.t.get("jitter_px", 4))
                    self.bot.stats["walls_upgraded"] = self.bot.stats.get("walls_upgraded", 0) + 1
                    self.bot._emit_stats()
                    log.info("Successfully upgraded a wall!")
                    self._settle(0.6, 1.0)
                    self.close_modal()
                    return 1

                self.close_modal()
        except Exception as ex:
            log.error("Error during wall upgrade: %s", ex)
            self.close_modal()
            
        return 0

    def run_upgrade_cycle(self) -> dict:
        """Execute full village upgrade sequence with strict Anti-Gem safeguards."""
        if not self.is_enabled():
            log.debug("Auto-upgrade is disabled in config.")
            return {"buildings": 0, "lab": 0, "walls": 0}

        log.info("=== Starting Village Upgrade Cycle ===")
        b_count = 0

        # Pre-cycle builder check: Do not attempt any building upgrades if 0 builders free!
        _, gray = self.bot.grab()
        free_b = self.get_free_builders(gray)
        builders_busy = self.check_builders_busy(gray)
        if free_b == 0 or builders_busy:
            log.info("All builders are busy (free=%d, busy=%s). Skipping building upgrades.", free_b, builders_busy)
        else:
            log.info("Free builders detected: %s. Proceeding with building upgrades.", free_b if free_b > 0 else "Available")
            # 1. Builder menu suggestions
            b_count += self.upgrade_suggested_buildings()

            # 2. If builders are still available, execute direct village building scan
            _, gray = self.bot.grab()
            if not self.check_builders_busy(gray):
                b_count += self.upgrade_village_buildings()

        # 3. Laboratory Research (independent of village builders)
        l_count = self.upgrade_laboratory()

        # 4. Wall Upgrades (resource dump, only if builder free)
        w_count = 0
        _, gray = self.bot.grab()
        if not self.check_builders_busy(gray):
            w_count = self.upgrade_walls()

        summary = {"buildings": b_count, "lab": l_count, "walls": w_count}
        log.info("=== Upgrade Cycle Finished: %s ===", summary)
        return summary
