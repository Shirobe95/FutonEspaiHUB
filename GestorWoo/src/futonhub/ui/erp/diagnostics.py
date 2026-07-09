from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from futonhub.core.config import load_settings
from futonhub.core.diagnostics import collect_diagnostics
from futonhub.core.guard import active_locks, clear_stale_locks
from futonhub.ui.theme import C_BG, apply_theme
from futonhub.ui.windowing import center_window


class DiagnosticsMixin:
    def _database_status_text(self) -> str:
        try:
            settings = load_settings()
            exists = settings.db_path.exists()
            status = "OK" if exists else "NO ENCONTRADA"
            return f"Base activa: {settings.db_path} - {status}"
        except Exception as exc:
            return f"Base activa: no se pudo comprobar - {exc}"

    def _safety_status_text(self) -> str:
        try:
            settings = load_settings()
            if settings.db_path.exists():
                clear_stale_locks(settings.db_path)
                locks = active_locks(settings.db_path)
                lock_text = "sin bloqueos activos" if not locks else f"{len(locks)} bloqueo(s) activo(s)"
            else:
                lock_text = "base no encontrada"
            return f"Modo: {settings.app_mode} - Maquina: {settings.machine_name} - Seguridad: {lock_text}"
        except Exception as exc:
            return f"Seguridad: no se pudo comprobar - {exc}"

    def _show_diagnostics(self) -> None:
        try:
            result = collect_diagnostics()
        except Exception as exc:
            messagebox.showerror(
                "Diagnostico del sistema",
                f"No se pudo generar el diagnostico.\n\n{exc}",
            )
            return

        window = tk.Toplevel(self)
        window.title("Diagnostico del sistema")
        center_window(window, 860, 620)
        window.minsize(760, 520)
        window.configure(bg=C_BG)
        apply_theme(window)

        frame = ttk.Frame(window, padding=18)
        frame.pack(fill=tk.BOTH, expand=True)

        title = "Diagnostico del sistema"
        if not result.ok:
            title += " - revisar avisos"
        ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor=tk.W, pady=(0, 10))

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        text = tk.Text(text_frame, wrap=tk.NONE, height=24)
        text.insert("1.0", result.text)
        text.configure(state=tk.DISABLED)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        y_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text.yview)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text.configure(yscrollcommand=y_scroll.set)

        button_bar = ttk.Frame(frame)
        button_bar.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(button_bar, text="Cerrar", command=window.destroy).pack(side=tk.RIGHT)

    def _show_text_window(self, title: str, body: str) -> None:
        window = tk.Toplevel(self)
        window.title(title)
        center_window(window, 940, 620)
        window.minsize(760, 520)
        window.configure(bg=C_BG)
        apply_theme(window)

        frame = ttk.Frame(window, padding=18)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor=tk.W, pady=(0, 10))

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        text = tk.Text(text_frame, wrap=tk.NONE, height=24)
        text.insert("1.0", body)
        text.configure(state=tk.DISABLED)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text.yview)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text.configure(yscrollcommand=y_scroll.set)

        button_bar = ttk.Frame(frame)
        button_bar.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(button_bar, text="Cerrar", command=window.destroy).pack(side=tk.RIGHT)
