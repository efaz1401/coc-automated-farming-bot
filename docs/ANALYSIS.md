# Bot Architecture Analysis & Implementation Plan

## 1. Reference bot pipeline (ko9ma7, cracked)

```
master_loop(accounts)
└─ per account:
   ├─ clear_popups_and_recover()      # claim/continue/skip/okay/close-X + blind X taps
   ├─ zoom_out() + normalize_camera() # recenter village view
   ├─ detect_de_availability()        # pixel color @HUD DE bar
   ├─ cek_status_resource()           # HSV pixel sample: gold/elixir/DE full?
   └─ cycle: farm-until-full → auto_upgrade_building/lab → next account

battle_sequence()
├─ clear_popups_and_recover(); handle_connection_lost()
├─ attack_home → find_match → load_saved_army (preset)
├─ wait_for_match_found(): watch "searching_opponents" DISAPPEAR,
│   on timeout/DC → force_restart_coc()  (am force-stop + am start)
├─ deploy_brutal():
│   ├─ detect_troop_slots(): empty_slot template per slot,
│   │   gray zone (0.40-0.58) decided by RGB variance  <-- key trick
│   ├─ hero/siege slots via template-in-bar → ability timers
│   └─ troops: long-press swipe-hold (2200ms) at jittered points
├─ loot wait 20-30s (DC check every 5s)
└─ surrender → confirm → home (fixed coords + DC checks)
```

Reliability DNA (shared with MyBot / ClashFarmer):
**never trust a tap** — every action is preceded by popup/DC sweeps and followed
by a state verification; escalation ladder = retry → close dialog → back key →
force app restart; all loops bounded.

## 2. Our gaps (before this change)

- Linear blind sequencing; one missed tap desynced the whole cycle.
- No disconnect / "Reload" / personal-break / maintenance handling.
- Battle end waited a fixed 55 s even if the fight ended at 10 s.
- Troop deploy relied on a brightness heuristic on 3 fixed slots.
- No storage-full awareness (farmed even with overflowing storages).
- No zoom/camera normalization (hardcoded building taps drift).

## 3. What was implemented

| Piece | File | Summary |
|---|---|---|
| Screen-state classifier | `bot/state.py` | HOME/ATTACK_MENU/CLOUDS/SCOUT/BATTLE/BATTLE_END/RELOAD/LOADING/UNKNOWN; template-free dialog heuristics |
| Recovery engine | `bot/recovery.py` | `clear_popups`, `handle_connection_lost`, `force_restart_coc`, `ensure_home` (3-level escalation, verified) |
| Dynamic army deploy | `bot/army.py` | slot detection via colorfulness+stddev (optional empty_slot template), swipe-hold deploy, config fallback |
| Storage sensing | `bot/vision.py` | `read_storage_fill()` HSV fill-ratio per resource bar |
| Integration | `bot/bot.py` | `ensure_home` gates the loop; state-driven `search_loop`/`end_battle`; storage skip; DC checks in clouds |
| Config | `config.yaml` | `states:`, `army:`, `storage:` sections (all optional, safe defaults) |
| Regression tests | `tests/run_tests.py` | synthetic screens for classifier, slot detection, storage fill |

## 4. Known limits (honest list)

- True 2-finger pinch zoom-out is not possible over stock `adb shell input`;
  we normalize camera by recenter swipes and (optionally) app restart, which
  resets CoC's saved zoom.
- Reload/DC dialog heuristics prefer templates when present
  (`assets/reload_button.png`, `assets/try_again.png`, `assets/okay_button.png`);
  without them, a green-button + dark-overlay heuristic with a fractional
  fallback tap is used.
- Deploy swipe-hold needs `input swipe` support (all major emulators OK).
