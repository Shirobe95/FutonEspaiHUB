from __future__ import annotations

from tkinter import ttk


C_BG = "#F6F7F9"
C_PANEL = "#FFFFFF"
C_PANEL_LINE = "#DDE3EA"
C_INFO = "#F1F5F9"
C_BTN = "#2563EB"
C_BTN_HOVER = "#1D4ED8"
C_BTN_ACTIVE = "#1E40AF"
C_EXPORT = "#0F766E"
C_EXPORT_HOVER = "#0D9488"
C_EXPORT_ACTIVE = "#115E59"
C_BTN_FG = "#FFFFFF"
C_LBL = "#1F2937"
C_MUTED = "#64748B"
C_GREY = "#94A3B8"
C_ERR = "#B91C1C"
C_OK = "#15803D"
C_RIGHT = "#EEF2F7"

FONT_TITLE = ("Segoe UI", 24, "bold")
FONT_SECTION = ("Segoe UI", 15, "bold")
FONT_BODY = ("Segoe UI", 10)
FONT_BODY_BOLD = ("Segoe UI", 10, "bold")
FONT_BUTTON = ("Segoe UI", 10, "bold")


def apply_theme(root: object) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(".", font=FONT_BODY, background=C_BG, foreground=C_LBL)
    style.configure("TFrame", background=C_BG)
    style.configure("Panel.TFrame", background=C_PANEL)
    style.configure("Info.TFrame", background=C_INFO)
    style.configure("Toolbar.TFrame", background=C_PANEL)
    style.configure("Footer.TFrame", background=C_BG)

    style.configure("TLabel", background=C_BG, foreground=C_LBL)
    style.configure("Panel.TLabel", background=C_PANEL, foreground=C_LBL)
    style.configure("Muted.TLabel", background=C_BG, foreground=C_MUTED)
    style.configure("PanelMuted.TLabel", background=C_PANEL, foreground=C_MUTED)
    style.configure("Title.TLabel", background=C_BG, foreground=C_LBL, font=FONT_TITLE)
    style.configure("Section.TLabel", background=C_PANEL, foreground=C_LBL, font=FONT_SECTION)
    style.configure("Status.TLabel", background=C_BG, foreground=C_MUTED)

    style.configure(
        "TButton",
        font=FONT_BUTTON,
        padding=(14, 8),
        borderwidth=0,
        relief="flat",
        background=C_BTN,
        foreground=C_BTN_FG,
    )
    style.map(
        "TButton",
        background=[("active", C_BTN_HOVER), ("pressed", C_BTN_ACTIVE)],
        foreground=[("disabled", C_GREY), ("!disabled", C_BTN_FG)],
    )
    style.configure(
        "Secondary.TButton",
        background=C_EXPORT,
        foreground=C_BTN_FG,
    )
    style.map(
        "Secondary.TButton",
        background=[("active", C_EXPORT_HOVER), ("pressed", C_EXPORT_ACTIVE)],
        foreground=[("disabled", C_GREY), ("!disabled", C_BTN_FG)],
    )

    style.configure(
        "TEntry",
        fieldbackground=C_PANEL,
        foreground=C_LBL,
        bordercolor=C_PANEL_LINE,
        lightcolor=C_PANEL_LINE,
        darkcolor=C_PANEL_LINE,
        padding=4,
    )
    style.configure(
        "TCombobox",
        fieldbackground=C_PANEL,
        background=C_PANEL,
        foreground=C_LBL,
        arrowcolor=C_BTN,
        bordercolor=C_PANEL_LINE,
        lightcolor=C_PANEL_LINE,
        darkcolor=C_PANEL_LINE,
        padding=4,
    )
    style.map("TCombobox", fieldbackground=[("readonly", C_PANEL)])

    style.configure(
        "Treeview",
        background=C_PANEL,
        fieldbackground=C_PANEL,
        foreground=C_LBL,
        bordercolor=C_PANEL_LINE,
        rowheight=26,
    )
    style.configure(
        "Treeview.Heading",
        background=C_INFO,
        foreground=C_LBL,
        font=FONT_BODY_BOLD,
        relief="flat",
        padding=(6, 6),
    )
    style.map("Treeview", background=[("selected", C_BTN)], foreground=[("selected", C_BTN_FG)])

    style.configure("Horizontal.TScrollbar", background=C_INFO, troughcolor=C_BG)
    style.configure("Vertical.TScrollbar", background=C_INFO, troughcolor=C_BG)
    style.configure("TNotebook", background=C_BG, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(12, 7), background=C_INFO, foreground=C_LBL)
    style.map("TNotebook.Tab", background=[("selected", C_PANEL)], foreground=[("selected", C_BTN)])

    return style
