from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tkinter import messagebox, ttk

from futonhub.ui.erp.models import ProjectAction
from futonhub.ui.erp.window_focus import find_window_for_process, restore_and_focus_window


class ProjectLaunchingMixin:
    def _launch_coste_pedido_placeholder(self) -> None:
        messagebox.showinfo(
            "Herramienta pendiente",
            "Aun falta definir la logica de Calculo de Coste de Pedido.",
        )

    def _launch_custom(
        self,
        key: str,
        path: Path,
        command: tuple[str, ...],
        window_title: str,
    ) -> None:
        action = ProjectAction(
            name=key,
            description="",
            path=path,
            command=command,
            window_title=window_title,
        )
        self._launch(action)

    def _launch(self, project: ProjectAction) -> None:
        process = self._processes.get(project.name)
        if process is not None and process.poll() is None:
            self._bring_to_front(project, process)
            return

        if not project.path.exists():
            messagebox.showerror(
                "Ruta no encontrada",
                f"No existe la carpeta:\n{project.path}",
            )
            return

        try:
            process = subprocess.Popen(
                project.command,
                cwd=project.path,
                close_fds=True,
            )
        except OSError as exc:
            messagebox.showerror(
                "No se pudo abrir",
                f"No se pudo arrancar {project.name}.\n\n{exc}",
            )
            return

        self._processes[project.name] = process
        self._set_button_open(project.name)
        self.after(500, lambda: self._bring_to_front(project, process))

    def _poll_processes(self) -> None:
        for project_name, process in list(self._processes.items()):
            if process.poll() is not None:
                self._processes.pop(project_name, None)
                self._set_button_closed(project_name)
        self.after(1000, self._poll_processes)

    def _set_button_open(self, project_name: str) -> None:
        button = self._buttons.get(project_name)
        if button is not None:
            button.configure(text="Abierta - traer al frente")

    def _set_button_closed(self, project_name: str) -> None:
        button = self._buttons.get(project_name)
        if button is not None:
            button.configure(text=self._button_closed_text.get(project_name, f"Abrir {project_name}"))

    def _bring_to_front(
        self,
        project: ProjectAction,
        process: subprocess.Popen[object],
    ) -> None:
        if sys.platform != "win32":
            return

        hwnd = find_window_for_process(process.pid, project.window_title)
        if hwnd is None:
            return
        restore_and_focus_window(hwnd)
