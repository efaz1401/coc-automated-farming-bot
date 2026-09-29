"""Live test: detect + dismiss the inactivity disconnect dialog, then verify home."""
import logging
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stdout)

from bot.bot import Bot, load_config
from bot.state import ScreenState

bot = Bot(load_config())
bot.adb.ensure_connected()

st, reason = bot.current_state()
print("BEFORE:", st.value, "|", reason)

handled = bot.recovery.handle_connection_lost()
print("HANDLE_DC:", handled)

# wait for reload to finish, then check state
time.sleep(6)
st2, reason2 = bot.current_state()
print("AFTER:", st2.value, "|", reason2)

ok = bot.recovery.ensure_home()
print("ENSURE_HOME:", ok)
st3, r3 = bot.current_state()
print("FINAL:", st3.value, "|", r3)
print("DC_TEST", "PASSED" if (handled and st3 is ScreenState.HOME) else "CHECK_MANUALLY")
