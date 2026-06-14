from __future__ import annotations

import sys


def find_window_for_process(pid: int, title_hint: str) -> int | None:
    if sys.platform != "win32":
        return None

    import ctypes

    user32 = ctypes.windll.user32
    matches: list[int] = []

    enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True

        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value != pid:
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True

        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if title_hint.lower() in title.lower():
            matches.append(hwnd)
            return False
        if not matches:
            matches.append(hwnd)
        return True

    user32.EnumWindows(enum_windows_proc(callback), 0)
    return matches[0] if matches else None


def restore_and_focus_window(hwnd: int) -> None:
    if sys.platform != "win32":
        return

    import ctypes

    user32 = ctypes.windll.user32
    sw_restore = 9
    user32.ShowWindow(hwnd, sw_restore)
    user32.SetForegroundWindow(hwnd)
