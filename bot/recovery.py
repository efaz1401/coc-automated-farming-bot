"""Recovery engine: popups, disconnects, app restart, verified return-to-home.

Design rules (cracked from production bots):
  - Never trust a tap: every recovery action is followed by re-classification.
  - Bounded everything: no unbounded retry loops; escalate instead.
  - Escalation ladder: clear popups -> back key -> force app restart.
"""
from __future__ import annotations
import logging
import time

from .state import ScreenState, classify, looks_like_reload_dialog

log = logging.getLogger("coc.recovery")

COC_PACKAGE = "com.supercell.clashofclans"
COC_ACTIVITY = ".GameApp"

DIALOG_BUTTON_FRAC = (0.50, 0.56)   # centered green "Reload"/"Try Again"/"Okay"
RELOAD_TEXT_FRAC = (0.33, 0.60)     # text-link "RELOAD GAME" (inactivity dialog)


class Recovery:
    def __init__(self, bot):
        self.bot = bot
        self.restart_count = 0

    # ---------- low-level ----------
    def _classify_now(self) -> tuple[ScreenState, str]:
        img, gray = self.bot.grab()
        return classify(img, gray, self.bot.vis, self.bot.cfg)

    def _back(self, times: int = 1):
        for _ in range(times):
            if self.bot._stop_event.is_set():
                return
            self.bot.adb_keyevent(4)
            self.bot.sleep_interruptible(0.8)

    # ---------- popups ----------
    def clear_popups(self, rounds: int = 4) -> int:
        """Close event/reward/misc popups. Returns how many were dismissed."""
        bot = self.bot
        closed = 0
        for _ in range(rounds):
            if bot._stop_event.is_set():
                break
            img, gray = bot.grab()
            tapped = False
            for key in ("close_modal", "close_x", "okay_button",
                        "event_continue", "claim_reward"):
                if bot.tap_match(gray, key, thresh=0.72):
                    closed += 1
                    tapped = True
                    break
            if not tapped and looks_like_reload_dialog(img, gray):
                bot.tap_frac(*DIALOG_BUTTON_FRAC)
                closed += 1
                tapped = True
            if not tapped:
                break
            bot.sleep_interruptible(1.2)
        if closed:
            log.info("cleared %d popup(s)", closed)
        return closed

    # ---------- connection lost ----------
    def handle_connection_lost(self) -> bool:
        """Detect & dismiss connection-lost / reload dialogs. True if handled."""
        bot = self.bot
        try:
            img, gray = bot.grab()
        except Exception as e:
            log.warning("grab failed in DC handler: %s", e)
            return False
        state, reason = classify(img, gray, bot.vis, bot.cfg)
        if state is not ScreenState.RELOAD_DIALOG:
            return False
        log.warning("connection/reload dialog detected (%s) — dismissing", reason)
        tapped = False
        for key in ("reload_button", "try_again", "okay_button"):
            if bot.tap_match(gray, key, thresh=0.72):
                tapped = True
                break
        if not tapped:
            # heuristic: green-button style dialog OR text-link "RELOAD GAME"
            # style dialog (inactivity). Try both canonical spots.
            from .state import looks_like_reload_dialog
            if looks_like_reload_dialog(img, gray):
                bot.tap_frac(*DIALOG_BUTTON_FRAC)
            else:
                bot.tap_frac(*RELOAD_TEXT_FRAC)
        bot.sleep_interruptible(6.0)
        # sometimes it takes two rounds
        try:
            img, gray = bot.grab()
            state2, _ = classify(img, gray, bot.vis, bot.cfg)
            if state2 is ScreenState.RELOAD_DIALOG:
                if not bot.tap_match(gray, "reload_button", thresh=0.72):
                    bot.tap_frac(*RELOAD_TEXT_FRAC)
                bot.sleep_interruptible(6.0)
        except Exception:
            pass
        return True

    # ---------- app restart ----------
    def force_restart_coc(self) -> bool:
        """Kill & relaunch CoC, wait until the village is up, clear popups."""
        bot = self.bot
        self.restart_count += 1
        log.warning("force-restarting CoC (attempt #%d)", self.restart_count)
        bot.adb_shell(f"am force-stop {COC_PACKAGE}")
        bot.sleep_interruptible(2.0)
        bot.adb_shell(f"am start -n {COC_PACKAGE}/{COC_PACKAGE}{COC_ACTIVITY}")
        bot.set_phase("Restarting Game")
        t0 = time.time()
        while time.time() - t0 < 90:
            if bot._stop_event.is_set():
                return False
            bot.sleep_interruptible(3.0)
            try:
                state, reason = self._classify_now()
            except Exception as e:
                log.debug("classify during restart failed: %s", e)
                continue
            log.debug("restart wait: %s (%s)", state.value, reason)
            if state is ScreenState.HOME:
                self.clear_popups()
                return True
            if state is ScreenState.RELOAD_DIALOG:
                self.handle_connection_lost()
        log.error("CoC did not reach home within 90s of restart")
        return False

    # ---------- the gatekeeper ----------
    def ensure_home(self, max_attempts: int = 3) -> bool:
        """Guarantee the bot ends up on the home village screen (or False).

        Level 0: already home.
        Level 1: state-appropriate dismissal (popups, back key, end battle).
        Level 2: force app restart.
        """
        bot = self.bot
        for attempt in range(1, max_attempts + 1):
            if bot._stop_event.is_set():
                return False
            try:
                state, reason = self._classify_now()
            except Exception as e:
                log.warning("classify failed (%s); retrying", e)
                bot.sleep_interruptible(2.0)
                continue
            log.info("ensure_home [%d/%d]: state=%s (%s)",
                     attempt, max_attempts, state.value, reason)

            if state is ScreenState.HOME:
                return True
            if state is ScreenState.LOADING:
                bot.sleep_interruptible(4.0)
                continue
            if state is ScreenState.RELOAD_DIALOG:
                self.handle_connection_lost()
                continue
            if state is ScreenState.BATTLE_END:
                _, gray = bot.grab()
                if not bot.tap_match(gray, "return_home"):
                    fb = bot.f.get("return_home_fallback", [0.5, 0.92])
                    bot.tap_frac(fb[0], fb[1])
                bot.sleep_interruptible(4.0)
                continue
            if state is ScreenState.BATTLE:
                log.warning("battle in progress during ensure_home — ending it")
                bot.end_battle()
                continue
            if state in (ScreenState.ATTACK_MENU, ScreenState.SCOUT,
                         ScreenState.CLOUDS):
                # leave matchmaking / scouting without fighting
                self._back(1)
                bot.sleep_interruptible(1.5)
                try:
                    img, gray = bot.grab()
                    st2, _ = classify(img, gray, bot.vis, bot.cfg)
                    if st2 in (ScreenState.SCOUT, ScreenState.CLOUDS):
                        m = bot.vis.find(gray, "surrender_button")
                        if m:
                            bot.adb.tap(m[0], m[1], bot.t.get("jitter_px", 4))
                            bot.sleep_interruptible(1.0)
                            bot.tap_match(bot.grab()[1], "confirm_surrender")
                            bot.sleep_interruptible(2.0)
                except Exception:
                    pass
                continue
            # UNKNOWN: game may not even be in the foreground — check & launch.
            fg = bot.adb_shell(
                "dumpsys activity activities | grep mResumedActivity")
            if COC_PACKAGE not in fg:
                log.warning("CoC not in foreground (focus=%s) — launching", fg[:80])
                bot.adb_shell(f"am start -n {COC_PACKAGE}/{COC_PACKAGE}{COC_ACTIVITY}")
                bot.sleep_interruptible(8.0)
                continue
            # CoC is foreground but unrecognized: popup sweep, back key,
            # and finally a full app restart on the last attempt.
            self.clear_popups()
            if attempt < max_attempts:
                self._back(1)
            else:
                return self.force_restart_coc()
        return False
