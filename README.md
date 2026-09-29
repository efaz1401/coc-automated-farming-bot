# Clash of Clans Farming Bot & Visual Studio

Automates **farming (dead-base collector raids)** via an Android emulator + ADB + OpenCV, now featuring both a **Desktop Visual GUI** and a **Browser Web Control Suite** for easy calibration, live screen monitoring, and bot management.

`Next`s through villages until loot meets your thresholds, drops troops on collectors, surrenders, retrains, repeats — with human-like timing and anti-ban breaks.

> ⚠️ Bots violate Supercell's ToS and can get your account **banned**. Use a throwaway / don't bot 24/7. This is for education.

---

## 1. Quick Start: Browser Web UI

Launch the Web UI server to control the bot through any web browser (or via `/browser`):
```powershell
python web.py
# or
python main.py --web
```
Open your browser at **`http://localhost:8080`**:
- **📊 Dashboard**: Live emulator screen feed, real-time loot statistics (Gold, Elixir, Dark Elixir), search/skip/attack counters, and one-click Start / Pause / Stop controls.
- **🎯 Template & Calibration Studio**: Visual manager for all 8 button templates and digits 0-9. Drag-to-crop directly on live emulator screenshots and automatic loot box ROI calibration.
- **⚙️ Settings & Strategy**: Visual configuration editor to set minimum loot, anti-ban tap delays, break schedules, and troop deployment settings with instant reload.
- **📜 Activity Logs**: Real-time streaming colored event log feed with clipboard copy and log clearing.

---

## 2. Desktop Visual GUI

Alternatively, run the native desktop application:
```powershell
python main.py
# or
python gui.py
```
*Tip: You can also click the **🌐 Web UI** button in the desktop GUI header to start the web server and open it in your browser simultaneously.*

---

## 3. Emulator & ADB Setup

1. Install an emulator (BlueStacks / LDPlayer / MEmu), set resolution **1280x720 landscape**, enable **ADB debugging**.
   - **BlueStacks**: Settings → Advanced → Android Debug Bridge ON.
   - **LDPlayer**: Settings → Advanced → ADB debugging.
2. Open Clash of Clans in the emulator and keep your village loaded on screen.
3. In either the Web UI or Desktop GUI top bar, select your device from the dropdown or enter `127.0.0.1:5555` and click **Connect**.

---

## 4. Visual Template Calibration (Required Once)

The bot finds buttons by image matching. With the Visual Studio (Desktop or Web), you don't need manual coordinate math:

1. Go to the **Template & Calibration Studio** tab.
2. Click **Grab Screen** or navigate your emulator to each required game screen.
3. Click **✂️ Crop** next to any missing button (e.g. `attack_button`, `next_button`).
4. Drag a rectangle around the button on the canvas and press **💾 Save Template**.
5. To calibrate loot reading, navigate to an enemy base during scout, click **🎯 Calibrate Gold Box from Live Screen**, and drag over the Gold number. The UI automatically calculates Elixir and Dark Elixir offsets!

### Button Templates Reference
| Template Key | What to crop |
|---|---|
| `attack_button` | Orange Attack button (village screen) |
| `find_match` | Find a Match button |
| `next_button` | Next button (scouting) |
| `surrender_button` | White-flag Surrender button |
| `confirm_surrender` | Okay/confirm popup |
| `return_home` | Return Home button |
| `train_button` | Train troops button |
| `quick_train` | Quick Train army button |
| `digits/0.png` … `9.png` | Loot-number digits (crop tightly) |

---

## 5. Command-Line & Headless Options

- **Run in headless terminal**:
  ```powershell
  python main.py --cli
  ```

- **Single scout and detection test**:
  ```powershell
  python main.py --once
  ```

- **Run Web Server on custom port**:
  ```powershell
  python web.py --port 5000 --open
  ```

---

## 6. Reliability Architecture (state machine + recovery)

The bot never trusts a tap. Every cycle is gated by a screen-state machine:

- **States** (`bot/state.py`): `home_village`, `attack_menu`, `clouds`, `scout`, `battle`,
  `battle_end`, `reload_dialog`, `loading`, `unknown` — classified from templates plus
  template-free heuristics (green-button + dim-overlay for disconnect dialogs).
- **Recovery** (`bot/recovery.py`): popup sweeping, connection-lost dismissal,
  `force_restart_coc()` (kill + relaunch via ADB), and `ensure_home()` with a bounded
  escalation ladder: popups → back key → app relaunch → force restart.
- **Dynamic army deploy** (`bot/army.py`): scans the troop bar slot grid and detects
  filled slots via icon colorfulness/stddev (optional `empty_slot` template override),
  then wave-deploys with swipe-holds. Falls back to legacy fixed-slot taps.
- **Storage sensing** (`Vision.read_storage_fill`): HSV fill-ratio of the HUD bars
  (CoC bars fill right→left from the icon side); farming idles when full
  (`farming.skip_attack_when_full`).
- **Battle end**: polled state detection instead of a fixed sleep — the bot leaves a
  finished fight immediately and still force-surrenders at `surrender_after_sec`.

Validate everything against the live emulator without attacking:
```powershell
python tools/validate_live.py
```

---

## 7. Running the Test Suite

Run the full regression test suite covering OCR binarization, digit parsing, dark elixir evaluation logic, interruptible sleep, desktop GUI components, web server REST API endpoints, the screen-state classifier, storage fill sensing, and army slot detection:
```powershell
python tests/run_tests.py
```
*(All 68 tests passing)*
