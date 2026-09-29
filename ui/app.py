"""Main Desktop GUI Application for Clash of Clans Farming Bot."""
from __future__ import annotations
import datetime as dt
import logging
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import cv2
import numpy as np
from PIL import Image, ImageTk
import yaml

from bot.adb import AdbDevice
from bot.bot import Bot, load_config
from bot.vision import Vision
from ui.crop_dialog import CropDialog
from ui.theme import COLORS, FONTS, apply_theme

log = logging.getLogger("coc")

BUTTON_DEFINITIONS = [
    ("attack_button", "Attack Button", "Orange attack button on village screen (bottom-left)"),
    ("find_match", "Find a Match", "Attack menu find match button"),
    ("next_button", "Next Button", "Scouting view next village button (bottom-right)"),
    ("surrender_button", "Surrender Button", "Battle white-flag surrender button (bottom-left)"),
    ("confirm_surrender", "Confirm Surrender", "Confirmation popup 'Okay' button"),
    ("return_home", "Return Home", "Battle end screen return home button"),
    ("train_button", "Train Button", "Village train troops button (bottom-right)"),
    ("quick_train", "Quick Train", "Training screen quick train button"),
    ("builder_face", "Builder Menu Icon", "Top-bar builder icon to open suggested upgrades"),
    ("suggested_upgrades", "Suggested Upgrades Header", "Header of the builder drop-down list"),
    ("all_builders_busy", "All Builders Busy", "Notice when 0 builders are currently available"),
    ("upgrade_button", "Upgrade Action Button", "Green Upgrade button below building info"),
    ("confirm_upgrade_gold", "Confirm Gold Upgrade", "Confirmation button for Gold upgrades"),
    ("confirm_upgrade_elixir", "Confirm Elixir Upgrade", "Confirmation button for Elixir upgrades"),
    ("confirm_upgrade_hero", "Confirm Hero Upgrade", "Confirmation button for Hero upgrades"),
    ("confirm_upgrade_de", "Confirm Dark Elixir Upgrade", "Confirmation button for DE upgrades"),
    ("btn_lab_confirm", "Laboratory Research Confirm", "Confirmation button for Lab troop/spell research"),
    ("lab_busy", "Laboratory Busy", "Notice when research is active in the Lab"),
    ("close_modal", "Close Dialog (X)", "Close X button to dismiss upgrade and info modals"),
    ("collect_gold", "Collect Gold", "Gold mine collector bubble icon"),
    ("collect_elixir", "Collect Elixir", "Elixir collector bubble icon"),
    ("shield_info", "Shield Info", "Top bar shield/guard status icon"),
    ("battle_end", "Battle End", "Battle victory/defeat indicator"),
    ("btn_lab_confirm_de", "Laboratory Research DE Confirm", "Confirmation button for Lab DE troop/spell research"),
    ("zero_builders", "Zero Builders Counter", "Zero free builders number indicator"),
    ("confirm_text", "Confirm Text", "Generic confirmation text button"),
    ("upgrade_button_dim", "Upgrade Disabled", "Grayed-out upgrade button when resources are insufficient"),
]


class QueueLogHandler(logging.Handler):
    """Thread-safe logging handler routing log records to a queue."""
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put((record.levelname, msg))
        except Exception:
            pass


class BotGUI:
    def __init__(self, root: tk.Tk, config_path: str = "config.yaml"):
        self.root = root
        self.config_path = config_path
        self.root.title("Clash of Clans Farming Bot — Visual Control Suite")
        self.root.geometry("1160x780")
        self.root.minsize(1020, 680)

        # Style & Theme
        self.style = apply_theme(self.root)

        # Load configuration
        self.cfg = load_config(self.config_path)
        self.bot = Bot(self.cfg)

        # Log queue
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._setup_logging()

        # State tracking
        self.last_screen_bgr: np.ndarray | None = None
        self.preview_tk: ImageTk.PhotoImage | None = None
        self.auto_refresh_screen = tk.BooleanVar(value=False)
        self.show_loot_overlay = tk.BooleanVar(value=True)

        # Build UI layout
        self._build_header()
        self._build_tabs()

        # Wire bot callbacks
        self._wire_bot()

        # Start periodic UI polling
        self.root.after(100, self._process_log_queue)
        self.root.after(1000, self._refresh_devices)
        self.root.after(1000, self._auto_screen_loop)

    def _setup_logging(self):
        handler = QueueLogHandler(self.log_queue)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        handler.setFormatter(fmt)
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def _wire_bot(self):
        def on_status(phase):
            self.root.after(0, lambda: self._update_phase_ui(phase))

        def on_stats(stats):
            self.root.after(0, lambda: self._update_stats_ui(stats))

        def on_screen(img, gray):
            self.last_screen_bgr = img
            self.root.after(0, lambda: self._display_screen_preview(img))

        self.bot.on_status = on_status
        self.bot.on_stats = on_stats
        self.bot.on_screen = on_screen

    # =========================================================================
    # Header: ADB Connection Bar & Bot Control Panel
    # =========================================================================
    def _build_header(self):
        header = tk.Frame(self.root, bg=COLORS["bg_header"], height=70, bd=0)
        header.pack(side=tk.TOP, fill=tk.X)

        # Left: App Brand & Connection
        left_box = tk.Frame(header, bg=COLORS["bg_header"])
        left_box.pack(side=tk.LEFT, padx=15, pady=10)

        lbl_title = tk.Label(
            left_box,
            text="⚔️ CoC Farming Bot",
            bg=COLORS["bg_header"],
            fg=COLORS["accent_blue"],
            font=FONTS["title"],
        )
        lbl_title.pack(anchor=tk.W)

        conn_frame = tk.Frame(left_box, bg=COLORS["bg_header"])
        conn_frame.pack(anchor=tk.W, pady=(3, 0))

        tk.Label(conn_frame, text="ADB Device:", bg=COLORS["bg_header"], fg=COLORS["text_secondary"], font=FONTS["small"]).pack(side=tk.LEFT)

        self.cmb_devices = ttk.Combobox(conn_frame, width=16, state="readonly")
        self.cmb_devices.pack(side=tk.LEFT, padx=(5, 5))
        self.cmb_devices.bind("<<ComboboxSelected>>", self._on_device_selected)

        btn_scan = ttk.Button(conn_frame, text="🔄 Scan", width=6, command=self._refresh_devices)
        btn_scan.pack(side=tk.LEFT, padx=(0, 10))

        self.ent_connect_addr = ttk.Entry(conn_frame, width=15)
        self.ent_connect_addr.insert(0, "127.0.0.1:5555")
        self.ent_connect_addr.pack(side=tk.LEFT, padx=(0, 5))

        btn_connect = ttk.Button(conn_frame, text="Connect", width=8, command=self._on_connect_clicked)
        btn_connect.pack(side=tk.LEFT)

        self.lbl_conn_status = tk.Label(
            conn_frame,
            text="● Disconnected",
            bg=COLORS["bg_header"],
            fg=COLORS["danger"],
            font=FONTS["small"],
        )
        self.lbl_conn_status.pack(side=tk.LEFT, padx=(10, 0))

        # Right: Bot Action Buttons & State Badge
        right_box = tk.Frame(header, bg=COLORS["bg_header"])
        right_box.pack(side=tk.RIGHT, padx=15, pady=10)

        self.lbl_phase_badge = tk.Label(
            right_box,
            text="IDLE",
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
            font=FONTS["bold"],
            padx=12,
            pady=4,
            relief="solid",
            bd=1,
        )
        self.lbl_phase_badge.pack(side=tk.LEFT, padx=(0, 15))

        self.btn_start = ttk.Button(right_box, text="▶ START BOT", style="Start.TButton", command=self._on_start_bot)
        self.btn_start.pack(side=tk.LEFT, padx=4)

        self.btn_pause = ttk.Button(right_box, text="⏸ PAUSE", style="Pause.TButton", command=self._on_pause_bot)
        self.btn_pause.pack(side=tk.LEFT, padx=4)

        self.btn_stop = ttk.Button(right_box, text="⏹ STOP", style="Stop.TButton", command=self._on_stop_bot)
        self.btn_stop.pack(side=tk.LEFT, padx=4)

        self.btn_web = ttk.Button(right_box, text="🌐 Web UI", command=self._on_launch_web_ui)
        self.btn_web.pack(side=tk.LEFT, padx=(10, 0))

    # =========================================================================
    # Tabs Notebook
    # =========================================================================
    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Tab 1: Dashboard
        self.tab_dashboard = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_dashboard, text="📊 Dashboard")
        self._build_dashboard_tab()

        # Tab 2: Calibration & Vision Studio
        self.tab_calibration = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_calibration, text="🎯 Template & Calibration Studio")
        self._build_calibration_tab()

        # Tab 3: Settings & Strategy
        self.tab_settings = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_settings, text="⚙️ Settings & Strategy")
        self._build_settings_tab()

        # Tab 4: Live Logs
        self.tab_logs = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_logs, text="📜 Activity Logs")
        self._build_logs_tab()

    # =========================================================================
    # Tab 1: Dashboard
    # =========================================================================
    def _build_dashboard_tab(self):
        container = tk.Frame(self.tab_dashboard, bg=COLORS["bg_main"])
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left Column: Screen Preview
        left_col = tk.Frame(container, bg=COLORS["bg_card"], bd=1, relief="solid")
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5), pady=0)

        preview_header = tk.Frame(left_col, bg=COLORS["bg_card"])
        preview_header.pack(fill=tk.X, padx=12, pady=8)

        tk.Label(
            preview_header,
            text="Live Emulator Display (1280x720)",
            bg=COLORS["bg_card"],
            fg=COLORS["accent_blue"],
            font=FONTS["subtitle"],
        ).pack(side=tk.LEFT)

        chk_overlay = ttk.Checkbutton(preview_header, text="Show Loot Regions", variable=self.show_loot_overlay, command=self._redraw_screen)
        chk_overlay.pack(side=tk.RIGHT, padx=5)

        chk_auto = ttk.Checkbutton(preview_header, text="Auto-Refresh (2s)", variable=self.auto_refresh_screen)
        chk_auto.pack(side=tk.RIGHT, padx=5)

        # Screen Canvas: 640 x 360 (fits neatly 16:9)
        self.screen_canvas = tk.Canvas(left_col, width=640, height=360, bg="#0d0e15", highlightthickness=0)
        self.screen_canvas.pack(anchor=tk.CENTER, pady=10)

        # Screen Actions Bar
        actions_bar = tk.Frame(left_col, bg=COLORS["bg_card"])
        actions_bar.pack(fill=tk.X, padx=12, pady=(0, 10))

        ttk.Button(actions_bar, text="📸 Grab Screen", command=self._on_manual_grab).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions_bar, text="🔍 Test OCR on Screen", command=self._on_test_ocr).pack(side=tk.LEFT, padx=3)
        ttk.Button(actions_bar, text="🎯 Scan Visible Buttons", command=self._on_test_buttons).pack(side=tk.LEFT, padx=3)

        self.lbl_screen_info = tk.Label(actions_bar, text="", bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["small"])
        self.lbl_screen_info.pack(side=tk.RIGHT, padx=5)

        # Right Column: Stat Cards & Live Info
        right_col = tk.Frame(container, bg=COLORS["bg_main"], width=420)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))
        right_col.pack_propagate(False)

        # Card 1: Resources Looted
        loot_card = tk.Frame(right_col, bg=COLORS["bg_card"], bd=1, relief="solid")
        loot_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(loot_card, text="Loot Farmed This Session", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["heading"]).pack(anchor=tk.W, padx=12, pady=(8, 4))

        stats_row = tk.Frame(loot_card, bg=COLORS["bg_card"])
        stats_row.pack(fill=tk.X, padx=12, pady=(0, 10))

        # Gold
        gold_box = tk.Frame(stats_row, bg=COLORS["bg_card"])
        gold_box.pack(side=tk.LEFT, expand=True)
        tk.Label(gold_box, text="GOLD", bg=COLORS["bg_card"], fg=COLORS["accent_gold"], font=FONTS["stat_lbl"]).pack()
        self.lbl_stat_gold = tk.Label(gold_box, text="0", bg=COLORS["bg_card"], fg=COLORS["accent_gold"], font=FONTS["stat_num"])
        self.lbl_stat_gold.pack()

        # Elixir
        elixir_box = tk.Frame(stats_row, bg=COLORS["bg_card"])
        elixir_box.pack(side=tk.LEFT, expand=True)
        tk.Label(elixir_box, text="ELIXIR", bg=COLORS["bg_card"], fg=COLORS["accent_elixir"], font=FONTS["stat_lbl"]).pack()
        self.lbl_stat_elixir = tk.Label(elixir_box, text="0", bg=COLORS["bg_card"], fg=COLORS["accent_elixir"], font=FONTS["stat_num"])
        self.lbl_stat_elixir.pack()

        # Dark Elixir
        dark_box = tk.Frame(stats_row, bg=COLORS["bg_card"])
        dark_box.pack(side=tk.LEFT, expand=True)
        tk.Label(dark_box, text="DARK ELIXIR", bg=COLORS["bg_card"], fg=COLORS["accent_dark"], font=FONTS["stat_lbl"]).pack()
        self.lbl_stat_dark = tk.Label(dark_box, text="0", bg=COLORS["bg_card"], fg=COLORS["accent_dark"], font=FONTS["stat_num"])
        self.lbl_stat_dark.pack()

        # Card 2: Farming & Upgrades Operations
        ops_card = tk.Frame(right_col, bg=COLORS["bg_card"], bd=1, relief="solid")
        ops_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(ops_card, text="Farming & Village Activity", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["heading"]).pack(anchor=tk.W, padx=12, pady=(8, 6))

        grid = tk.Frame(ops_card, bg=COLORS["bg_card"])
        grid.pack(fill=tk.X, padx=12, pady=(0, 10))

        tk.Label(grid, text="Searches Conducted:", bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["body"]).grid(row=0, column=0, sticky="w", pady=2)
        self.lbl_stat_searches = tk.Label(grid, text="0", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["bold"])
        self.lbl_stat_searches.grid(row=0, column=1, sticky="e", padx=10)

        tk.Label(grid, text="Villages Skipped:", bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["body"]).grid(row=1, column=0, sticky="w", pady=2)
        self.lbl_stat_skips = tk.Label(grid, text="0", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["bold"])
        self.lbl_stat_skips.grid(row=1, column=1, sticky="e", padx=10)

        tk.Label(grid, text="Bases Attacked:", bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["body"]).grid(row=2, column=0, sticky="w", pady=2)
        self.lbl_stat_attacks = tk.Label(grid, text="0", bg=COLORS["bg_card"], fg=COLORS["success"], font=FONTS["bold"])
        self.lbl_stat_attacks.grid(row=2, column=1, sticky="e", padx=10)

        tk.Label(grid, text="Buildings Upgraded:", bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["body"]).grid(row=3, column=0, sticky="w", pady=2)
        self.lbl_stat_buildings = tk.Label(grid, text="0", bg=COLORS["bg_card"], fg=COLORS["accent_gold"], font=FONTS["bold"])
        self.lbl_stat_buildings.grid(row=3, column=1, sticky="e", padx=10)

        tk.Label(grid, text="Lab Researches:", bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["body"]).grid(row=4, column=0, sticky="w", pady=2)
        self.lbl_stat_lab = tk.Label(grid, text="0", bg=COLORS["bg_card"], fg=COLORS["accent_elixir"], font=FONTS["bold"])
        self.lbl_stat_lab.grid(row=4, column=1, sticky="e", padx=10)

        tk.Label(grid, text="Session Uptime:", bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["body"]).grid(row=5, column=0, sticky="w", pady=2)
        self.lbl_stat_uptime = tk.Label(grid, text="00:00:00", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["mono"])
        self.lbl_stat_uptime.grid(row=5, column=1, sticky="e", padx=10)

        grid.columnconfigure(0, weight=1)

        # Card 3: Quick Tools & Diagnostics
        tools_card = tk.Frame(right_col, bg=COLORS["bg_card"], bd=1, relief="solid")
        tools_card.pack(fill=tk.BOTH, expand=True)

        tk.Label(tools_card, text="Quick Actions & Fallbacks", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["heading"]).pack(anchor=tk.W, padx=12, pady=(8, 6))

        tools_btn_frame = tk.Frame(tools_card, bg=COLORS["bg_card"])
        tools_btn_frame.pack(fill=tk.X, padx=12, pady=4)

        ttk.Button(tools_btn_frame, text="🔨 Upgrade Village Now", command=self._on_upgrade_village_now).pack(fill=tk.X, pady=3)
        ttk.Button(tools_btn_frame, text="⚡ Single Scout & Eval (--once)", command=self._on_run_once).pack(fill=tk.X, pady=3)
        ttk.Button(tools_btn_frame, text="🏠 Emergency Return Home", command=self._on_emergency_return_home).pack(fill=tk.X, pady=3)
        ttk.Button(tools_btn_frame, text="🔄 Reset Statistics", command=self._on_reset_stats).pack(fill=tk.X, pady=3)

    # =========================================================================
    # Tab 2: Template & Calibration Studio
    # =========================================================================
    def _build_calibration_tab(self):
        container = tk.Frame(self.tab_calibration, bg=COLORS["bg_main"])
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left side: Button templates list
        left_frame = tk.Frame(container, bg=COLORS["bg_card"], bd=1, relief="solid")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        tk.Label(
            left_frame,
            text="Button Recognition Templates",
            bg=COLORS["bg_card"],
            fg=COLORS["accent_blue"],
            font=FONTS["subtitle"],
        ).pack(anchor=tk.W, padx=12, pady=(10, 4))

        tk.Label(
            left_frame,
            text="The bot detects these buttons by image matching. Capture them from your emulator.",
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
            font=FONTS["small"],
        ).pack(anchor=tk.W, padx=12, pady=(0, 8))

        # Scrollable buttons container
        btn_scroll_canvas = tk.Canvas(left_frame, bg=COLORS["bg_card"], highlightthickness=0)
        btn_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=btn_scroll_canvas.yview)
        self.btn_scroll_frame = tk.Frame(btn_scroll_canvas, bg=COLORS["bg_card"])

        self.btn_scroll_frame.bind(
            "<Configure>",
            lambda e: btn_scroll_canvas.configure(scrollregion=btn_scroll_canvas.bbox("all")),
        )
        btn_scroll_canvas.create_window((0, 0), window=self.btn_scroll_frame, anchor="nw")
        btn_scroll_canvas.configure(yscrollcommand=btn_scroll.set)

        btn_scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
        btn_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        self.template_rows = {}
        self._populate_template_rows()

        # Right side: Loot Box & Digits Calibrator
        right_frame = tk.Frame(container, bg=COLORS["bg_main"], width=420)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))
        right_frame.pack_propagate(False)

        # Digits panel
        digits_card = tk.Frame(right_frame, bg=COLORS["bg_card"], bd=1, relief="solid")
        digits_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(digits_card, text="Loot Digit Templates (0-9)", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["heading"]).pack(anchor=tk.W, padx=12, pady=(8, 4))
        tk.Label(digits_card, text="Digits are used to read Gold, Elixir, and DE numbers on the scout screen.", bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["small"]).pack(anchor=tk.W, padx=12, pady=(0, 8))

        self.digits_grid = tk.Frame(digits_card, bg=COLORS["bg_card"])
        self.digits_grid.pack(fill=tk.X, padx=12, pady=(0, 10))
        self.digit_widgets = {}
        self._populate_digits_grid()

        # Loot Boxes Calibrator panel
        loot_box_card = tk.Frame(right_frame, bg=COLORS["bg_card"], bd=1, relief="solid")
        loot_box_card.pack(fill=tk.BOTH, expand=True)

        tk.Label(loot_box_card, text="Scout Loot Boxes Calibration", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["heading"]).pack(anchor=tk.W, padx=12, pady=(8, 4))
        tk.Label(loot_box_card, text="Defines the fractional regions on the scout screen for reading resources.", bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["small"]).pack(anchor=tk.W, padx=12, pady=(0, 8))

        boxes_grid = tk.Frame(loot_box_card, bg=COLORS["bg_card"])
        boxes_grid.pack(fill=tk.X, padx=12, pady=5)

        self.ent_loot_boxes = {}
        vcfg = self.cfg.get("vision", {}).get("loot_boxes", {})
        for idx, (res, label_color) in enumerate([
            ("gold", COLORS["accent_gold"]),
            ("elixir", COLORS["accent_elixir"]),
            ("dark", COLORS["accent_dark"]),
        ]):
            tk.Label(boxes_grid, text=res.capitalize() + ":", bg=COLORS["bg_card"], fg=label_color, font=FONTS["bold"]).grid(row=idx, column=0, sticky="w", pady=4)
            val = vcfg.get(res, [0.06, 0.10 + idx * 0.07, 0.16, 0.06])
            ent = ttk.Entry(boxes_grid, width=28)
            ent.insert(0, str(val))
            ent.grid(row=idx, column=1, sticky="w", padx=6, pady=4)
            self.ent_loot_boxes[res] = ent

        ttk.Button(
            loot_box_card,
            text="🎯 Calibrate Gold Box from Live Screen",
            style="Primary.TButton",
            command=self._on_calibrate_loot_box,
        ).pack(fill=tk.X, padx=12, pady=(10, 4))

        ttk.Button(
            loot_box_card,
            text="💾 Save Loot Boxes to Config",
            command=self._on_save_loot_boxes,
        ).pack(fill=tk.X, padx=12, pady=4)

    def _populate_template_rows(self):
        for widget in self.btn_scroll_frame.winfo_children():
            widget.destroy()

        tpl_status = self.bot.vis.get_template_status()
        self.template_thumbnails = {}

        for key, title, desc in BUTTON_DEFINITIONS:
            row = tk.Frame(self.btn_scroll_frame, bg=COLORS["bg_card"], bd=1, relief="solid")
            row.pack(fill=tk.X, expand=True, padx=4, pady=4)

            # Thumbnail canvas (50x50)
            thumb_canvas = tk.Canvas(row, width=50, height=50, bg="#11111b", highlightthickness=1, highlightbackground=COLORS["border"])
            thumb_canvas.pack(side=tk.LEFT, padx=8, pady=6)

            st = tpl_status.get(key, {})
            p = st.get("path", "")
            if p and os.path.exists(p):
                try:
                    thumb_img = Image.open(p)
                    thumb_img.thumbnail((48, 48))
                    tk_img = ImageTk.PhotoImage(thumb_img)
                    self.template_thumbnails[key] = tk_img
                    thumb_canvas.create_image(25, 25, image=tk_img, anchor=tk.CENTER)
                except Exception:
                    pass

            # Title + Desc
            info_frame = tk.Frame(row, bg=COLORS["bg_card"])
            info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

            title_row = tk.Frame(info_frame, bg=COLORS["bg_card"])
            title_row.pack(fill=tk.X)

            tk.Label(title_row, text=title, bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["bold"]).pack(side=tk.LEFT)

            # Status Badge
            exists = st.get("exists", False)
            status_text = "✅ Ready" if exists else "❌ Missing"
            status_fg = COLORS["success"] if exists else COLORS["danger"]
            tk.Label(title_row, text=status_text, bg=COLORS["bg_card"], fg=status_fg, font=FONTS["small"]).pack(side=tk.LEFT, padx=10)

            tk.Label(info_frame, text=desc, bg=COLORS["bg_card"], fg=COLORS["text_muted"], font=FONTS["small"]).pack(anchor=tk.W)

            # Crop button
            btn_crop = ttk.Button(row, text="✂️ Crop", width=8, command=lambda k=key: self._on_crop_template(k))
            btn_crop.pack(side=tk.RIGHT, padx=10)

    def _populate_digits_grid(self):
        for widget in self.digits_grid.winfo_children():
            widget.destroy()

        dig_status = self.bot.vis.get_digit_status()
        self.digit_thumbs = {}

        for d in range(10):
            ch = str(d)
            cell = tk.Frame(self.digits_grid, bg=COLORS["bg_card"], bd=1, relief="solid")
            cell.grid(row=d // 5, column=d % 5, padx=3, pady=3, sticky="nsew")

            exists = dig_status.get(ch, False)
            color = COLORS["success"] if exists else COLORS["danger"]
            lbl_title = tk.Label(cell, text=f"'{ch}'", bg=COLORS["bg_card"], fg=color, font=FONTS["bold"])
            lbl_title.pack(pady=(2, 0))

            path = os.path.join("assets", "digits", f"{ch}.png")
            thumb_c = tk.Canvas(cell, width=28, height=28, bg="#11111b", highlightthickness=0)
            thumb_c.pack(pady=2)
            if exists and os.path.exists(path):
                try:
                    img = Image.open(path)
                    img.thumbnail((26, 26))
                    tk_img = ImageTk.PhotoImage(img)
                    self.digit_thumbs[ch] = tk_img
                    thumb_c.create_image(14, 14, image=tk_img, anchor=tk.CENTER)
                except Exception:
                    pass

            btn = ttk.Button(cell, text="Crop", width=4, command=lambda c=ch: self._on_crop_digit(c))
            btn.pack(pady=(0, 2))

        for c in range(5):
            self.digits_grid.columnconfigure(c, weight=1)

    # =========================================================================
    # Tab 3: Settings & Strategy
    # =========================================================================
    def _build_settings_tab(self):
        container = tk.Frame(self.tab_settings, bg=COLORS["bg_main"])
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left Column: Targets & Automation
        left_col = tk.Frame(container, bg=COLORS["bg_card"], bd=1, relief="solid")
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        tk.Label(left_col, text="Loot Requirements & Search Limits", bg=COLORS["bg_card"], fg=COLORS["accent_blue"], font=FONTS["subtitle"]).pack(anchor=tk.W, padx=15, pady=(12, 6))

        grid = tk.Frame(left_col, bg=COLORS["bg_card"])
        grid.pack(fill=tk.X, padx=15, pady=5)

        farm_cfg = self.cfg.get("farming", {})

        # Min Gold
        tk.Label(grid, text="Min Gold:", bg=COLORS["bg_card"], fg=COLORS["accent_gold"], font=FONTS["bold"]).grid(row=0, column=0, sticky="w", pady=6)
        self.ent_min_gold = ttk.Entry(grid, width=15)
        self.ent_min_gold.insert(0, str(farm_cfg.get("min_gold", 400000)))
        self.ent_min_gold.grid(row=0, column=1, sticky="w", padx=10)

        # Min Elixir
        tk.Label(grid, text="Min Elixir:", bg=COLORS["bg_card"], fg=COLORS["accent_elixir"], font=FONTS["bold"]).grid(row=1, column=0, sticky="w", pady=6)
        self.ent_min_elixir = ttk.Entry(grid, width=15)
        self.ent_min_elixir.insert(0, str(farm_cfg.get("min_elixir", 400000)))
        self.ent_min_elixir.grid(row=1, column=1, sticky="w", padx=10)

        # Min Dark
        tk.Label(grid, text="Min Dark Elixir (0=ignore):", bg=COLORS["bg_card"], fg=COLORS["accent_dark"], font=FONTS["bold"]).grid(row=2, column=0, sticky="w", pady=6)
        self.ent_min_dark = ttk.Entry(grid, width=15)
        self.ent_min_dark.insert(0, str(farm_cfg.get("min_dark", 2000)))
        self.ent_min_dark.grid(row=2, column=1, sticky="w", padx=10)

        # Max Searches
        tk.Label(grid, text="Max Nexts Before Cooldown:", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["body"]).grid(row=3, column=0, sticky="w", pady=6)
        self.ent_max_searches = ttk.Entry(grid, width=15)
        self.ent_max_searches.insert(0, str(farm_cfg.get("max_searches", 60)))
        self.ent_max_searches.grid(row=3, column=1, sticky="w", padx=10)

        # Surrender wait
        tk.Label(grid, text="Surrender Wait (seconds):", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["body"]).grid(row=4, column=0, sticky="w", pady=6)
        self.ent_surrender = ttk.Entry(grid, width=15)
        self.ent_surrender.insert(0, str(farm_cfg.get("surrender_after_sec", 55)))
        self.ent_surrender.grid(row=4, column=1, sticky="w", padx=10)

        # Checkboxes
        tk.Label(left_col, text="Base & Army Automation", bg=COLORS["bg_card"], fg=COLORS["accent_blue"], font=FONTS["subtitle"]).pack(anchor=tk.W, padx=15, pady=(16, 6))

        self.var_collect = tk.BooleanVar(value=farm_cfg.get("collect_resources", True))
        self.var_train = tk.BooleanVar(value=farm_cfg.get("train_army", True))
        self.var_shield = tk.BooleanVar(value=farm_cfg.get("check_shield", True))

        ttk.Checkbutton(left_col, text="Auto-collect resource mines before attack", variable=self.var_collect).pack(anchor=tk.W, padx=15, pady=2)
        ttk.Checkbutton(left_col, text="Auto-quick train army after each battle", variable=self.var_train).pack(anchor=tk.W, padx=15, pady=2)
        ttk.Checkbutton(left_col, text="Check shield info before attacking", variable=self.var_shield).pack(anchor=tk.W, padx=15, pady=2)

        # Village Upgrades Automation
        tk.Label(left_col, text="Village Auto-Upgrades", bg=COLORS["bg_card"], fg=COLORS["accent_blue"], font=FONTS["subtitle"]).pack(anchor=tk.W, padx=15, pady=(14, 6))

        upg_cfg = self.cfg.get("upgrades", {})
        self.var_upgrade_enabled = tk.BooleanVar(value=upg_cfg.get("enabled", True))
        self.var_upgrade_bld = tk.BooleanVar(value=upg_cfg.get("upgrade_buildings", True))
        self.var_upgrade_hero = tk.BooleanVar(value=upg_cfg.get("upgrade_heroes", True))
        self.var_upgrade_lab = tk.BooleanVar(value=upg_cfg.get("upgrade_lab", True))
        self.var_upgrade_wall = tk.BooleanVar(value=upg_cfg.get("upgrade_walls", True))

        ttk.Checkbutton(left_col, text="Master: Enable Village Auto-Upgrades", variable=self.var_upgrade_enabled).pack(anchor=tk.W, padx=15, pady=2)
        ttk.Checkbutton(left_col, text="Upgrade Buildings via Builder Menu", variable=self.var_upgrade_bld).pack(anchor=tk.W, padx=30, pady=2)
        ttk.Checkbutton(left_col, text="Upgrade Heroes when available", variable=self.var_upgrade_hero).pack(anchor=tk.W, padx=30, pady=2)
        ttk.Checkbutton(left_col, text="Upgrade Laboratory Troops & Spells", variable=self.var_upgrade_lab).pack(anchor=tk.W, padx=30, pady=2)
        ttk.Checkbutton(left_col, text="Upgrade Walls with excess resources", variable=self.var_upgrade_wall).pack(anchor=tk.W, padx=30, pady=2)

        # Right Column: Anti-Ban & Timing
        right_col = tk.Frame(container, bg=COLORS["bg_card"], bd=1, relief="solid")
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        tk.Label(right_col, text="Human-Like Timing & Anti-Ban", bg=COLORS["bg_card"], fg=COLORS["accent_blue"], font=FONTS["subtitle"]).pack(anchor=tk.W, padx=15, pady=(12, 6))

        grid2 = tk.Frame(right_col, bg=COLORS["bg_card"])
        grid2.pack(fill=tk.X, padx=15, pady=5)

        timing_cfg = self.cfg.get("timing", {})

        # Tap delay range
        tk.Label(grid2, text="Min Tap Delay (s):", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["body"]).grid(row=0, column=0, sticky="w", pady=6)
        self.ent_min_tap = ttk.Entry(grid2, width=15)
        self.ent_min_tap.insert(0, str(timing_cfg.get("min_tap_delay", 0.4)))
        self.ent_min_tap.grid(row=0, column=1, sticky="w", padx=10)

        tk.Label(grid2, text="Max Tap Delay (s):", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["body"]).grid(row=1, column=0, sticky="w", pady=6)
        self.ent_max_tap = ttk.Entry(grid2, width=15)
        self.ent_max_tap.insert(0, str(timing_cfg.get("max_tap_delay", 1.2)))
        self.ent_max_tap.grid(row=1, column=1, sticky="w", padx=10)

        # Tap Jitter
        tk.Label(grid2, text="Random Tap Jitter (px):", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["body"]).grid(row=2, column=0, sticky="w", pady=6)
        self.ent_jitter = ttk.Entry(grid2, width=15)
        self.ent_jitter.insert(0, str(timing_cfg.get("jitter_px", 4)))
        self.ent_jitter.grid(row=2, column=1, sticky="w", padx=10)

        # Break interval
        tk.Label(grid2, text="Take Long Break Every (min):", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["body"]).grid(row=3, column=0, sticky="w", pady=6)
        self.ent_break_interval = ttk.Entry(grid2, width=15)
        self.ent_break_interval.insert(0, str(timing_cfg.get("long_break_every_min", 45)))
        self.ent_break_interval.grid(row=3, column=1, sticky="w", padx=10)

        # Match threshold
        v_cfg = self.cfg.get("vision", {})
        tk.Label(grid2, text="Vision Match Threshold (0.0-1.0):", bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["body"]).grid(row=4, column=0, sticky="w", pady=6)
        self.ent_thresh = ttk.Entry(grid2, width=15)
        self.ent_thresh.insert(0, str(v_cfg.get("match_threshold", 0.82)))
        self.ent_thresh.grid(row=4, column=1, sticky="w", padx=10)

        # Save Button
        save_box = tk.Frame(right_col, bg=COLORS["bg_card"])
        save_box.pack(fill=tk.X, padx=15, pady=25)

        ttk.Button(save_box, text="💾 Save & Apply Settings", style="Primary.TButton", command=self._on_save_settings).pack(fill=tk.X)

    # =========================================================================
    # Tab 4: Live Logs
    # =========================================================================
    def _build_logs_tab(self):
        container = tk.Frame(self.tab_logs, bg=COLORS["bg_main"])
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        top_controls = tk.Frame(container, bg=COLORS["bg_header"], height=40)
        top_controls.pack(fill=tk.X, pady=(0, 5))

        tk.Label(top_controls, text="Live Activity & Diagnostics Log", bg=COLORS["bg_header"], fg=COLORS["accent_blue"], font=FONTS["subtitle"]).pack(side=tk.LEFT, padx=10, pady=6)

        ttk.Button(top_controls, text="Clear Log", width=10, command=self._clear_logs).pack(side=tk.RIGHT, padx=5, pady=6)
        ttk.Button(top_controls, text="Copy to Clipboard", width=16, command=self._copy_logs).pack(side=tk.RIGHT, padx=5, pady=6)

        self.txt_log = ScrolledText(
            container,
            bg="#11111b",
            fg=COLORS["text_primary"],
            insertbackground=COLORS["text_primary"],
            font=FONTS["mono"],
            wrap=tk.WORD,
            bd=1,
            relief="solid",
        )
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        self.txt_log.tag_config("INFO", foreground="#89b4fa")
        self.txt_log.tag_config("WARNING", foreground="#f9e2af")
        self.txt_log.tag_config("ERROR", foreground="#f38ba8")
        self.txt_log.tag_config("DEBUG", foreground="#6c7086")

    # =========================================================================
    # Log Processing & UI Updates
    # =========================================================================
    def _process_log_queue(self):
        while not self.log_queue.empty():
            try:
                level, msg = self.log_queue.get_nowait()
                self.txt_log.insert(tk.END, msg + "\n", level)
                self.txt_log.see(tk.END)
            except queue.Empty:
                break
        self.root.after(100, self._process_log_queue)

    def _clear_logs(self):
        self.txt_log.delete("1.0", tk.END)

    def _copy_logs(self):
        content = self.txt_log.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        messagebox.showinfo("Copied", "Log contents copied to clipboard.")

    def _update_phase_ui(self, phase: str):
        self.lbl_phase_badge.config(text=phase.upper())
        if phase in ("Idle", "Stopped", "ADB Error"):
            self.lbl_phase_badge.config(fg=COLORS["text_secondary"] if phase == "Idle" else COLORS["danger"])
            self.btn_start.config(state="normal")
            self.btn_pause.config(state="disabled", text="⏸ PAUSE")
            self.btn_stop.config(state="disabled")
        elif phase == "Paused":
            self.lbl_phase_badge.config(fg=COLORS["warning"])
            self.btn_pause.config(state="normal", text="▶ RESUME")
            self.btn_start.config(state="disabled")
            self.btn_stop.config(state="normal")
        else:
            # Any active phase (Collecting, Training, Searching, Upgrading, etc.)
            self.lbl_phase_badge.config(fg=COLORS["success"])
            self.btn_start.config(state="disabled")
            self.btn_pause.config(state="normal", text="⏸ PAUSE")
            self.btn_stop.config(state="normal")

    def _update_stats_ui(self, stats: dict):
        self.lbl_stat_searches.config(text=f"{stats.get('searches', 0):,}")
        self.lbl_stat_skips.config(text=f"{stats.get('skips', 0):,}")
        self.lbl_stat_attacks.config(text=f"{stats.get('attacks', 0):,}")
        self.lbl_stat_buildings.config(text=f"{stats.get('buildings_upgraded', 0):,}")
        self.lbl_stat_lab.config(text=f"{stats.get('lab_researches', 0):,}")
        self.lbl_stat_gold.config(text=f"{stats.get('loot_gold', 0):,}")
        self.lbl_stat_elixir.config(text=f"{stats.get('loot_elixir', 0):,}")
        self.lbl_stat_dark.config(text=f"{stats.get('loot_dark', 0):,}")

        started = stats.get("started")
        if started:
            elapsed = int((dt.datetime.now() - started).total_seconds())
            hours, rem = divmod(elapsed, 3600)
            mins, secs = divmod(rem, 60)
            self.lbl_stat_uptime.config(text=f"{hours:02d}:{mins:02d}:{secs:02d}")

    # =========================================================================
    # Screen Preview & Visualization
    # =========================================================================
    def _display_screen_preview(self, img_bgr: np.ndarray):
        self.last_screen_bgr = img_bgr
        disp = img_bgr.copy()

        # Overlay loot boxes if enabled
        if self.show_loot_overlay.get():
            H, W = disp.shape[:2]
            colors = {
                "gold": (0, 215, 255),    # BGR Yellow/Gold
                "elixir": (200, 50, 255),  # BGR Magenta/Elixir
                "dark": (255, 100, 100),  # BGR DE Blue/Purple
            }
            vcfg = self.cfg.get("vision", {}).get("loot_boxes", {})
            for name, box in vcfg.items():
                x, y = int(box[0] * W), int(box[1] * H)
                w, h = int(box[2] * W), int(box[3] * H)
                c = colors.get(name, (0, 255, 0))
                cv2.rectangle(disp, (x, y), (x + w, y + h), c, 2)
                cv2.putText(disp, name.upper(), (x, max(15, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, c, 1)

        disp_resized = cv2.resize(disp, (640, 360))
        disp_rgb = cv2.cvtColor(disp_resized, cv2.COLOR_BGR2RGB)
        self.preview_tk = ImageTk.PhotoImage(Image.fromarray(disp_rgb))
        self.screen_canvas.delete("all")
        self.screen_canvas.create_image(320, 180, image=self.preview_tk, anchor=tk.CENTER)

    def _redraw_screen(self):
        if self.last_screen_bgr is not None:
            self._display_screen_preview(self.last_screen_bgr)

    def _auto_screen_loop(self):
        if self.auto_refresh_screen.get() and not self.bot.is_running():
            threading.Thread(target=self._fetch_screen_background, daemon=True).start()
        self.root.after(2000, self._auto_screen_loop)

    def _fetch_screen_background(self):
        try:
            if self.bot.adb.ensure_connected():
                img, _ = self.bot.grab()
        except Exception:
            pass

    def _on_manual_grab(self):
        def _grab():
            try:
                if not self.bot.adb.ensure_connected():
                    self.root.after(0, lambda: messagebox.showwarning("No Device", "ADB device not connected."))
                    return
                img, _ = self.bot.grab()
                self.root.after(0, lambda: self.lbl_screen_info.config(text=f"Captured @ {dt.datetime.now():%H:%M:%S}"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Grab Error", str(e)))

        threading.Thread(target=_grab, daemon=True).start()

    def _on_test_ocr(self):
        if self.last_screen_bgr is None:
            messagebox.showinfo("No Screen", "Click 'Grab Screen' first to fetch a frame.")
            return
        loot = self.bot.vis.read_loot(self.last_screen_bgr)
        g, e, d = loot["gold"], loot["elixir"], loot["dark"]
        msg = f"Detected Loot on Current Screen:\n\n• Gold: {g:, if g >= 0 else 'UNREAD'}\n• Elixir: {e:, if e >= 0 else 'UNREAD'}\n• Dark Elixir: {d:, if d >= 0 else 'UNREAD'}"
        messagebox.showinfo("Loot OCR Test", msg)

    def _on_test_buttons(self):
        if self.last_screen_bgr is None:
            messagebox.showinfo("No Screen", "Click 'Grab Screen' first to fetch a frame.")
            return
        gray = cv2.cvtColor(self.last_screen_bgr, cv2.COLOR_BGR2GRAY)
        matches = self.bot.vis.find_all_matches(gray)
        if not matches:
            messagebox.showinfo("Button Match Test", "No loaded button templates matched the current screen.")
            return
        lines = [f"• {name}: score {data['score']:.2f} @ ({data['cx']}, {data['cy']})" for name, data in matches.items()]
        messagebox.showinfo("Buttons Detected", "Found buttons on screen:\n\n" + "\n".join(lines))

    # =========================================================================
    # ADB Device Management
    # =========================================================================
    def _refresh_devices(self):
        devices = AdbDevice.list_devices()
        serials = [d["serial"] for d in devices if d.get("state") == "device"]
        self.cmb_devices["values"] = serials
        if serials:
            if not self.bot.adb.serial or self.bot.adb.serial not in serials:
                self.cmb_devices.current(0)
                self.bot.adb.serial = serials[0]
            else:
                self.cmb_devices.set(self.bot.adb.serial)
            self.lbl_conn_status.config(text=f"● {self.bot.adb.serial}", fg=COLORS["success"])
        else:
            self.lbl_conn_status.config(text="● No Device", fg=COLORS["danger"])

    def _on_device_selected(self, event):
        val = self.cmb_devices.get().strip()
        if val:
            self.bot.adb.serial = val
            self.lbl_conn_status.config(text=f"● {val}", fg=COLORS["success"])
            log.info("Active ADB serial set to %s", val)

    def _on_connect_clicked(self):
        addr = self.ent_connect_addr.get().strip()
        if not addr:
            return

        def _do_conn():
            ok, msg = AdbDevice.connect_device(addr)
            if ok:
                self.root.after(0, self._refresh_devices)
                self.root.after(0, lambda: messagebox.showinfo("ADB Connected", f"Successfully connected to {addr}"))
            else:
                self.root.after(0, lambda: messagebox.showerror("ADB Connection Failed", msg))

        threading.Thread(target=_do_conn, daemon=True).start()

    # =========================================================================
    # Calibration & Cropping Helpers
    # =========================================================================
    def _on_crop_template(self, template_key: str):
        if self.last_screen_bgr is None:
            try:
                if self.bot.adb.ensure_connected():
                    self.last_screen_bgr, _ = self.bot.grab()
            except Exception:
                pass
        if self.last_screen_bgr is None:
            messagebox.showwarning("No Screen", "Cannot crop without an active emulator screenshot. Please grab a screen first.")
            return

        def on_saved(key, info):
            self.bot.vis.reload_templates()
            self._populate_template_rows()

        CropDialog(self.root, self.last_screen_bgr, template_key, target_type="button", on_saved=on_saved)

    def _on_crop_digit(self, digit_ch: str):
        if self.last_screen_bgr is None:
            try:
                if self.bot.adb.ensure_connected():
                    self.last_screen_bgr, _ = self.bot.grab()
            except Exception:
                pass
        if self.last_screen_bgr is None:
            messagebox.showwarning("No Screen", "Cannot crop without an active emulator screenshot. Please grab a screen first.")
            return

        def on_saved(key, info):
            self.bot.vis.reload_templates()
            self._populate_digits_grid()

        CropDialog(self.root, self.last_screen_bgr, digit_ch, target_type="digit", on_saved=on_saved)

    def _on_calibrate_loot_box(self):
        if self.last_screen_bgr is None:
            try:
                if self.bot.adb.ensure_connected():
                    self.last_screen_bgr, _ = self.bot.grab()
            except Exception:
                pass
        if self.last_screen_bgr is None:
            messagebox.showwarning("No Screen", "Please navigate your emulator to the scout screen and click 'Grab Screen' first.")
            return

        def on_saved(key, info):
            b = info.get("box")
            if b:
                # Update gold box and calculate standard elixir/dark offsets
                self.ent_loot_boxes["gold"].delete(0, tk.END)
                self.ent_loot_boxes["gold"].insert(0, str(b))

                elixir_b = [b[0], round(b[1] + 0.07, 3), b[2], b[3]]
                self.ent_loot_boxes["elixir"].delete(0, tk.END)
                self.ent_loot_boxes["elixir"].insert(0, str(elixir_b))

                dark_b = [b[0], round(b[1] + 0.14, 3), b[2], b[3]]
                self.ent_loot_boxes["dark"].delete(0, tk.END)
                self.ent_loot_boxes["dark"].insert(0, str(dark_b))

                self._on_save_loot_boxes()

        CropDialog(self.root, self.last_screen_bgr, "Gold Loot Region", target_type="loot_box", on_saved=on_saved)

    def _on_save_loot_boxes(self):
        try:
            boxes = {}
            for res in ("gold", "elixir", "dark"):
                raw = self.ent_loot_boxes[res].get().strip()
                boxes[res] = yaml.safe_load(raw)

            if "vision" not in self.cfg:
                self.cfg["vision"] = {}
            self.cfg["vision"]["loot_boxes"] = boxes

            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.cfg, f, default_flow_style=False)

            self.bot.reload_config(self.cfg)
            self._redraw_screen()
            messagebox.showinfo("Saved", "Loot boxes saved and reloaded successfully.")
        except Exception as e:
            messagebox.showerror("Error Saving Boxes", str(e))

    # =========================================================================
    # Settings & Strategy Save
    # =========================================================================
    def _on_save_settings(self):
        try:
            self.cfg["farming"]["min_gold"] = int(self.ent_min_gold.get())
            self.cfg["farming"]["min_elixir"] = int(self.ent_min_elixir.get())
            self.cfg["farming"]["min_dark"] = int(self.ent_min_dark.get())
            self.cfg["farming"]["max_searches"] = int(self.ent_max_searches.get())
            self.cfg["farming"]["surrender_after_sec"] = int(self.ent_surrender.get())
            self.cfg["farming"]["collect_resources"] = self.var_collect.get()
            self.cfg["farming"]["train_army"] = self.var_train.get()
            self.cfg["farming"]["check_shield"] = self.var_shield.get()

            self.cfg["timing"]["min_tap_delay"] = float(self.ent_min_tap.get())
            self.cfg["timing"]["max_tap_delay"] = float(self.ent_max_tap.get())
            self.cfg["timing"]["jitter_px"] = int(self.ent_jitter.get())
            self.cfg["timing"]["long_break_every_min"] = int(self.ent_break_interval.get())

            self.cfg["vision"]["match_threshold"] = float(self.ent_thresh.get())

            if "upgrades" not in self.cfg:
                self.cfg["upgrades"] = {}
            self.cfg["upgrades"]["enabled"] = self.var_upgrade_enabled.get()
            self.cfg["upgrades"]["upgrade_buildings"] = self.var_upgrade_bld.get()
            self.cfg["upgrades"]["upgrade_heroes"] = self.var_upgrade_hero.get()
            self.cfg["upgrades"]["upgrade_lab"] = self.var_upgrade_lab.get()
            self.cfg["upgrades"]["upgrade_walls"] = self.var_upgrade_wall.get()

            # Preserve active ADB serial so reload_config doesn't revert it
            if self.bot.adb.serial:
                self.cfg["emulator"]["adb_serial"] = self.bot.adb.serial

            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.cfg, f, default_flow_style=False)

            self.bot.reload_config(self.cfg)
            messagebox.showinfo("Saved", "Settings successfully saved to config.yaml and applied to active bot.")
        except Exception as e:
            messagebox.showerror("Error Saving Settings", str(e))

    # =========================================================================
    # Bot Control Actions
    # =========================================================================
    def _on_start_bot(self):
        if not self.bot.adb.ensure_connected():
            messagebox.showerror("No ADB Device", "Please connect an emulator or device via ADB before starting.")
            return

        missing = self.bot.vis.missing_templates()
        if missing:
            resp = messagebox.askyesno(
                "Missing Templates",
                f"The following templates are not captured yet:\n{', '.join(missing)}\n\n"
                "The bot may not be able to navigate the game menus without them.\n"
                "Do you want to start anyway?",
            )
            if not resp:
                return

        self.bot.start_in_thread()

    def _on_pause_bot(self):
        if self.bot.is_paused():
            self.bot.resume()
        else:
            self.bot.pause()

    def _on_stop_bot(self):
        self.bot.stop()

    def _on_reset_stats(self):
        self.bot.reset_stats()

    def _on_upgrade_village_now(self):
        if self.bot.is_running():
            messagebox.showwarning("Bot Running", "Please pause or stop the bot before running a manual upgrade cycle.")
            return

        def _task():
            try:
                if not self.bot.adb.ensure_connected():
                    self.root.after(0, lambda: messagebox.showerror("No Device", "No ADB device connected."))
                    return
                log.info("Running manual village upgrade cycle...")
                summary = self.bot.upgrade_village_now()
                msg = f"Upgrade Cycle Finished:\n• Buildings Upgraded: {summary.get('buildings', 0)}\n• Lab Researches: {summary.get('lab', 0)}\n• Walls Upgraded: {summary.get('walls', 0)}"
                self.root.after(0, lambda: messagebox.showinfo("Village Upgrade Complete", msg))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Upgrade Error", str(e)))

        threading.Thread(target=_task, daemon=True).start()

    def _on_run_once(self):
        if self.bot.is_running():
            messagebox.showwarning("Bot Running", "Please pause or stop the bot before running single scout test.")
            return

        def _once():
            try:
                if not self.bot.adb.ensure_connected():
                    self.root.after(0, lambda: messagebox.showerror("No Device", "No ADB device connected."))
                    return
                img, gray = self.bot.grab()
                loot = self.bot.vis.read_loot(img)
                matches = self.bot.vis.find_all_matches(gray)
                summary = [
                    f"Gold: {loot['gold']:, if loot['gold'] >= 0 else 'UNREAD'}",
                    f"Elixir: {loot['elixir']:, if loot['elixir'] >= 0 else 'UNREAD'}",
                    f"Dark Elixir: {loot['dark']:, if loot['dark'] >= 0 else 'UNREAD'}",
                    f"\nButtons Visible: {len(matches)}",
                ]
                for name, d in matches.items():
                    summary.append(f"  • {name} (score: {d['score']:.2f})")
                self.root.after(0, lambda: messagebox.showinfo("Single Scout Evaluation", "\n".join(summary)))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))

        threading.Thread(target=_once, daemon=True).start()

    def _on_emergency_return_home(self):
        if self.bot.is_running():
            self.bot.stop()

        def _ret():
            try:
                if not self.bot.adb.ensure_connected():
                    return
                m = self.bot.wait_for("return_home", timeout=3)
                if m:
                    self.bot.adb.tap(m[0], m[1])
                else:
                    fb = self.bot.f.get("return_home_fallback", [0.5, 0.92])
                    self.bot.tap_frac(fb[0], fb[1])
                log.info("Emergency return home tap sent")
            except Exception as e:
                log.warning("Emergency return home failed: %s", e)

        threading.Thread(target=_ret, daemon=True).start()

    def _on_launch_web_ui(self):
        import webbrowser
        from web.server import start_server
        port = 8088
        if not hasattr(self, "_web_server") or self._web_server is None:
            try:
                self._web_server = start_server(bot=self.bot, config_path=self.config_path, host="0.0.0.0", port=8088, block=False)
                port = self._web_server.port
            except Exception as e:
                log.info("Web server already running or port bound: %s", e)
        elif self._web_server:
            port = self._web_server.port
        webbrowser.open(f"http://localhost:{port}")


def main():
    root = tk.Tk()
    app = BotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
