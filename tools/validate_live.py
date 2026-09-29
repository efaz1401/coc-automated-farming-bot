"""Live end-to-end validation against the running emulator.

Run:  python tools/validate_live.py
Performs (in order, safe: no attacks, no spending):
  1. ADB connect + foreground app check
  2. ensure_home() — launches CoC if needed, clears popups, verifies village
  3. state classification on the real screen
  4. storage fill + village resource OCR on the real screen
  5. collector bubble scan (read-only)
"""
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stdout)

from bot.bot import Bot, load_config  # noqa: E402


def main():
    bot = Bot(load_config())
    print("=" * 60)
    print("[1] ADB connect:", bot.adb.ensure_connected(), "| serial:", bot.adb.serial)
    fg = bot.adb_shell("dumpsys activity activities | grep mResumedActivity")
    print("    foreground app:", (fg or "?")[:100])

    print("[2] ensure_home()...")
    ok = bot.recovery.ensure_home()
    print("    ENSURE_HOME_RESULT:", ok)

    print("[3] live classification:")
    st, reason = bot.current_state()
    print("    state:", st.value, "|", reason)

    print("[4] resource sensing:")
    img, gray = bot.grab()
    print("    storage fill:", bot.vis.read_storage_fill(img))
    print("    village OCR :", bot.vis.read_village_resources(img))
    print("    _storages_full:", bot._storages_full())

    print("[5] collector bubbles:")
    for key in ("collect_gold", "collect_elixir"):
        m = bot.vis.find(gray, key, 0.72)
        print(f"    {key}: {m}")

    print("=" * 60)
    print("LIVE VALIDATION", "PASSED" if ok else "FAILED")


if __name__ == "__main__":
    main()
