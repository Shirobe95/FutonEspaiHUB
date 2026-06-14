from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from gestorwoo.config import Settings, load_settings
from gestorwoo.guard import operation_lock
from gestorwoo.security import log_event
from gestorwoo.theme import C_BG, C_PANEL, C_PANEL_LINE, apply_theme


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    created_at: str
    size: int


class BackupManager:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.backup_dir = db_path.parent / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, reason: str = "manual") -> Path:
        if not self.db_path.exists():
            raise FileNotFoundError(f"No existe la base de datos: {self.db_path}")

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.backup_dir / f"gestorwoo-{timestamp}-{reason}.sqlite3"

        source_connection = sqlite3.connect(self.db_path)
        try:
            target_connection = sqlite3.connect(target)
            try:
                source_connection.backup(target_connection)
            finally:
                target_connection.close()
        finally:
            source_connection.close()

        return target

    def restore_backup(self, backup_path: Path) -> Path:
        if not backup_path.exists():
            raise FileNotFoundError(f"No existe el backup: {backup_path}")

        settings = load_settings()
        with operation_lock(
            settings,
            "restore_backup",
            module="Backups y Restauraciones",
            details=f"Restauracion desde {backup_path.name}",
            ttl_minutes=20,
        ):
            log_event(
                self.db_path,
                module="Backups y Restauraciones",
                action="Restaurar backup",
                status="STARTED",
                severity="WARNING",
                entity_type="backup",
                entity_id=backup_path.name,
                details=f"Restauracion solicitada desde {backup_path}",
            )
            pre_restore = self.create_backup("pre-restore") if self.db_path.exists() else None
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, self.db_path)
            log_event(
                self.db_path,
                module="Backups y Restauraciones",
                action="Restaurar backup",
                status="OK",
                severity="WARNING",
                entity_type="backup",
                entity_id=backup_path.name,
                details=f"Backup previo creado: {pre_restore.name if pre_restore else 'no aplica'}",
            )
            return pre_restore or backup_path

    def list_backups(self) -> list[BackupInfo]:
        backups = []
        for path in sorted(self.backup_dir.glob("*.sqlite3"), reverse=True):
            stat = path.stat()
            backups.append(
                BackupInfo(
                    path=path,
                    created_at=datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    size=stat.st_size,
                )
            )
        return backups


class BackupApp(tk.Tk):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.manager = BackupManager(settings.db_path)

        self.title("Futon Espai - Backups")
        self.geometry("900x560")
        self.minsize(760, 460)
        self.configure(bg=C_BG)
        apply_theme(self)

        self.status_text = tk.StringVar(value=f"Base protegida: {settings.db_path}")
        self._build_layout()
        self._load_backups()

    def _build_layout(self) -> None:
        header = ttk.Frame(self, padding=(14, 12, 14, 8))
        header.pack(fill=tk.X)
        ttk.Label(header, text="Backups y Restauracion", style="Title.TLabel").pack(
            anchor=tk.W
        )

        toolbar = ttk.Frame(self, padding=(14, 8, 14, 10), style="Toolbar.TFrame")
        toolbar.pack(fill=tk.X)

        ttk.Button(toolbar, text="Crear backup", command=self._create_backup).pack(
            side=tk.LEFT
        )
        ttk.Button(
            toolbar,
            text="Restaurar seleccionado",
            style="Secondary.TButton",
            command=self._restore_selected,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(toolbar, text="Restaurar desde archivo", command=self._restore_file).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(toolbar, text="Actualizar lista", command=self._load_backups).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )

        outer_table = tk.Frame(
            self,
            bg=C_PANEL,
            highlightbackground=C_PANEL_LINE,
            highlightthickness=1,
            bd=0,
        )
        outer_table.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 10))

        table_frame = ttk.Frame(outer_table, padding=(10, 10, 10, 8), style="Panel.TFrame")
        table_frame.pack(fill=tk.BOTH, expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("created_at", "name", "size", "path")
        headings = {
            "created_at": "Fecha",
            "name": "Backup",
            "size": "Tamano",
            "path": "Ruta",
        }
        widths = {
            "created_at": 150,
            "name": 260,
            "size": 100,
            "path": 360,
        }
        self.table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        for column in columns:
            self.table.heading(column, text=headings[column], anchor=tk.CENTER)
            self.table.column(column, width=widths[column], minwidth=80, anchor=tk.CENTER)

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        ttk.Label(
            self,
            textvariable=self.status_text,
            padding=(14, 4),
            anchor=tk.W,
            style="Status.TLabel",
        ).pack(fill=tk.X)

    def _load_backups(self) -> None:
        self.table.delete(*self.table.get_children())
        backups = self.manager.list_backups()
        for backup in backups:
            self.table.insert(
                "",
                tk.END,
                values=(
                    backup.created_at,
                    backup.path.name,
                    self._format_size(backup.size),
                    str(backup.path),
                ),
            )
        self.status_text.set(f"Backups disponibles: {len(backups)}")

    def _create_backup(self) -> None:
        try:
            path = self.manager.create_backup()
        except Exception as exc:
            messagebox.showerror("Backup fallido", str(exc))
            return
        self._load_backups()
        messagebox.showinfo("Backup creado", f"Backup guardado en:\n{path}")

    def _restore_selected(self) -> None:
        selected = self.table.selection()
        if not selected:
            messagebox.showwarning("Seleccion requerida", "Selecciona un backup.")
            return
        path = Path(self.table.item(selected[0], "values")[3])
        self._restore(path)

    def _restore_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Selecciona un backup SQLite",
            initialdir=self.manager.backup_dir,
            filetypes=[("SQLite", "*.sqlite3"), ("Todos los archivos", "*.*")],
        )
        if selected:
            self._restore(Path(selected))

    def _restore(self, path: Path) -> None:
        confirmed = messagebox.askyesno(
            "Confirmar restauracion",
            (
                "Se reemplazara la base local actual.\n\n"
                "Antes de restaurar se creara un backup de seguridad.\n\n"
                f"Backup a restaurar:\n{path}"
            ),
        )
        if not confirmed:
            return

        try:
            safety_backup = self.manager.restore_backup(path)
        except Exception as exc:
            messagebox.showerror("Restauracion fallida", str(exc))
            return
        self._load_backups()
        messagebox.showinfo(
            "Restauracion completada",
            f"Base restaurada.\n\nBackup previo guardado en:\n{safety_backup}",
        )

    def _format_size(self, value: int) -> str:
        if value >= 1024 * 1024:
            return f"{value / (1024 * 1024):.1f} MB"
        if value >= 1024:
            return f"{value / 1024:.1f} KB"
        return f"{value} B"


def run_backup_app(settings: Settings) -> None:
    app = BackupApp(settings)
    app.mainloop()
