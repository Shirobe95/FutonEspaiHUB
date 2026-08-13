from __future__ import annotations

import tkinter as tk


def clamped_window_size(
    width: int,
    height: int,
    screen_width: int,
    screen_height: int,
    *,
    margin: int = 40,
) -> tuple[int, int]:
    """Return a requested window size constrained to the usable viewport."""
    usable_width = max(1, int(screen_width) - (margin * 2))
    usable_height = max(1, int(screen_height) - (margin * 2))
    return min(int(width), usable_width), min(int(height), usable_height)


def center_window(window: tk.Tk | tk.Toplevel, width: int, height: int) -> None:
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    width, height = clamped_window_size(width, height, screen_width, screen_height)
    x = max((screen_width - width) // 2, 0)
    y = max((screen_height - height) // 2, 0)
    window.geometry(f"{width}x{height}+{x}+{y}")
