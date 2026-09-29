"""Theme and styling configuration for Clash of Clans Bot GUI."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

COLORS = {
    "bg_main": "#181825",
    "bg_card": "#1e1e2e",
    "bg_header": "#252538",
    "bg_input": "#11111b",
    "border": "#313244",
    "text_primary": "#cdd6f4",
    "text_secondary": "#a6adc8",
    "text_muted": "#6c7086",
    
    # Accent colors
    "accent_blue": "#89b4fa",
    "accent_gold": "#f9e2af",
    "accent_elixir": "#f38ba8",
    "accent_dark": "#cba6f7",
    "success": "#a6e3a1",
    "warning": "#f9e2af",
    "danger": "#f38ba8",
    
    # Buttons
    "btn_start": "#a6e3a1",
    "btn_stop": "#f38ba8",
    "btn_pause": "#f9e2af",
    "btn_text_dark": "#11111b",
}

FONTS = {
    "title": ("Segoe UI", 16, "bold"),
    "subtitle": ("Segoe UI", 12, "bold"),
    "heading": ("Segoe UI", 11, "bold"),
    "body": ("Segoe UI", 10),
    "bold": ("Segoe UI", 10, "bold"),
    "small": ("Segoe UI", 9),
    "mono": ("Consolas", 9),
    "stat_num": ("Segoe UI", 18, "bold"),
    "stat_lbl": ("Segoe UI", 8, "bold"),
}


def apply_theme(root: tk.Tk) -> ttk.Style:
    """Configures TTK styles and default Tk widget appearances."""
    root.configure(bg=COLORS["bg_main"])
    style = ttk.Style()
    
    # Use clam theme as foundation for dark customization
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Generic Frame
    style.configure("TFrame", background=COLORS["bg_main"])
    style.configure("Card.TFrame", background=COLORS["bg_card"], relief="flat")
    style.configure("Header.TFrame", background=COLORS["bg_header"], relief="flat")

    # Generic Label
    style.configure(
        "TLabel",
        background=COLORS["bg_main"],
        foreground=COLORS["text_primary"],
        font=FONTS["body"],
    )
    style.configure(
        "Card.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["text_primary"],
        font=FONTS["body"],
    )
    style.configure(
        "Muted.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["text_secondary"],
        font=FONTS["small"],
    )
    style.configure(
        "StatNum.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["accent_blue"],
        font=FONTS["stat_num"],
    )
    style.configure(
        "StatGold.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["accent_gold"],
        font=FONTS["stat_num"],
    )
    style.configure(
        "StatElixir.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["accent_elixir"],
        font=FONTS["stat_num"],
    )
    style.configure(
        "StatDark.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["accent_dark"],
        font=FONTS["stat_num"],
    )

    # Notebook Tabs
    style.configure(
        "TNotebook",
        background=COLORS["bg_main"],
        borderwidth=0,
    )
    style.configure(
        "TNotebook.Tab",
        background=COLORS["bg_card"],
        foreground=COLORS["text_secondary"],
        padding=[14, 8],
        font=FONTS["bold"],
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", COLORS["bg_header"]), ("active", COLORS["border"])],
        foreground=[("selected", COLORS["accent_blue"]), ("active", COLORS["text_primary"])],
    )

    # Buttons
    style.configure(
        "TButton",
        background=COLORS["bg_card"],
        foreground=COLORS["text_primary"],
        font=FONTS["bold"],
        borderwidth=1,
        relief="flat",
        padding=[10, 5],
    )
    style.map(
        "TButton",
        background=[("active", COLORS["border"]), ("pressed", COLORS["bg_header"])],
        foreground=[("active", "#ffffff")],
    )

    style.configure(
        "Primary.TButton",
        background=COLORS["accent_blue"],
        foreground=COLORS["btn_text_dark"],
        font=FONTS["bold"],
        borderwidth=0,
        padding=[12, 6],
    )
    style.map(
        "Primary.TButton",
        background=[("active", "#b4befe"), ("pressed", "#74c7ec")],
    )

    style.configure(
        "Start.TButton",
        background=COLORS["btn_start"],
        foreground=COLORS["btn_text_dark"],
        font=FONTS["bold"],
        borderwidth=0,
        padding=[14, 7],
    )
    style.map(
        "Start.TButton",
        background=[("active", "#bbf2b5"), ("pressed", "#94e2d5")],
    )

    style.configure(
        "Stop.TButton",
        background=COLORS["btn_stop"],
        foreground=COLORS["btn_text_dark"],
        font=FONTS["bold"],
        borderwidth=0,
        padding=[14, 7],
    )
    style.map(
        "Stop.TButton",
        background=[("active", "#f5c2e7"), ("pressed", "#eba0ac")],
    )

    style.configure(
        "Pause.TButton",
        background=COLORS["btn_pause"],
        foreground=COLORS["btn_text_dark"],
        font=FONTS["bold"],
        borderwidth=0,
        padding=[12, 6],
    )
    style.map(
        "Pause.TButton",
        background=[("active", "#fae3b0"), ("pressed", "#f5e0dc")],
    )

    # Entry & Combobox
    style.configure(
        "TEntry",
        fieldbackground=COLORS["bg_input"],
        foreground=COLORS["text_primary"],
        insertcolor=COLORS["text_primary"],
        font=FONTS["body"],
        padding=[6, 4],
    )
    style.configure(
        "TCombobox",
        fieldbackground=COLORS["bg_input"],
        background=COLORS["bg_card"],
        foreground=COLORS["text_primary"],
        arrowcolor=COLORS["text_primary"],
        font=FONTS["body"],
    )

    # Checkbutton
    style.configure(
        "TCheckbutton",
        background=COLORS["bg_card"],
        foreground=COLORS["text_primary"],
        font=FONTS["body"],
    )
    style.map(
        "TCheckbutton",
        background=[("active", COLORS["bg_card"])],
        foreground=[("active", COLORS["accent_blue"])],
    )

    return style
