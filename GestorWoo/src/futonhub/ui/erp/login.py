from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from futonhub.cloud.auth import SupabaseAuthError, register_device_seen, sign_in_with_password
from futonhub.core.config import load_settings
from futonhub.ui.theme import C_BG, C_PANEL, C_PANEL_LINE


class LoginMixin:
    def _effective_role(self) -> str | None:
        """Rol real para construir la interfaz.

        En modo Supabase no se muestra ninguna herramienta hasta tener sesión
        autenticada. Esto evita que el rol local del .env enseñe herramientas
        antes del login real.
        """
        try:
            settings = load_settings()
        except Exception:
            return None
        if settings.app_mode == "supabase_guarded":
            if self._cloud_session is None:
                return None
            return (self._cloud_session.role or "").lower() or None
        return (settings.sync_role or "").lower() or None

    def _is_authenticated_admin(self) -> bool:
        return (self._effective_role() or "") == "admin"

    def _has_cloud_session(self) -> bool:
        return self._cloud_session is not None

    def _role_status_text(self) -> str:
        try:
            settings = load_settings()
            if self._cloud_session is not None:
                role = self._cloud_session.role or settings.sync_role
                email = self._cloud_session.email or settings.hub_user_email or "sin usuario online"
                return f"Online: Supabase · Sesión activa · Rol: {role} · Usuario: {email}"
            role = settings.sync_role
            email = settings.hub_user_email or "sin usuario online"
            if settings.app_mode == "supabase_guarded":
                return f"Online: Supabase · Sin login · Rol local: {role} · Usuario: {email}"
            return f"Online: desactivado · Rol local: {role}"
        except Exception as exc:
            return f"Online: no se pudo comprobar · {exc}"

    def _show_login_overlay(self) -> tk.Frame:
        """Muestra el estado de login dentro de la ventana principal.

        Evita usar un Toplevel flotante para que, al mover el HUB, el aviso
        no quede perdido en otra zona del escritorio.
        """
        self._hide_login_overlay()
        overlay = tk.Frame(self, bg=C_BG, bd=0, highlightthickness=0)
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        overlay.lift()

        card = tk.Frame(
            overlay,
            bg=C_PANEL,
            bd=0,
            highlightbackground=C_PANEL_LINE,
            highlightthickness=1,
        )
        card.place(relx=0.5, rely=0.5, anchor=tk.CENTER, width=460, height=170)

        content = ttk.Frame(card, padding=20, style="Panel.TFrame")
        content.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            content,
            text="Iniciando sesión en Supabase...",
            style="Section.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            content,
            text="Validando usuario, rol y dispositivo. No cierres el HUB.",
            style="PanelMuted.TLabel",
        ).pack(anchor=tk.W, pady=(8, 0))
        bar = ttk.Progressbar(content, mode="indeterminate")
        bar.pack(fill=tk.X, pady=(18, 0))
        bar.start(10)
        self._login_overlay = overlay
        self.update_idletasks()
        return overlay

    def _hide_login_overlay(self) -> None:
        overlay = self._login_overlay
        self._login_overlay = None
        try:
            if overlay is not None and overlay.winfo_exists():
                overlay.destroy()
        except Exception:
            pass

    def _login_supabase(self) -> None:
        if self._login_in_progress:
            return
        try:
            settings = load_settings()
        except Exception as exc:
            messagebox.showerror("Login Supabase", f"No se pudo leer configuración.\n\n{exc}")
            return

        if settings.app_mode != "supabase_guarded":
            messagebox.showinfo(
                "Login Supabase",
                "El HUB no está en modo supabase_guarded. Revisa GestorWoo/.env.",
            )
            return

        email = simpledialog.askstring(
            "Login Supabase",
            "Email:",
            parent=self,
            initialvalue=settings.hub_user_email or "",
        )
        if not email:
            return
        password = simpledialog.askstring(
            "Login Supabase",
            f"Contraseña para {email}:",
            parent=self,
            show="*",
        )
        if not password:
            return

        self._login_in_progress = True
        self.configure(cursor="watch")
        progress = self._show_login_overlay()

        def worker() -> None:
            try:
                session = sign_in_with_password(email, password, settings)
                register_device_seen(session, settings)
            except Exception as exc:  # se muestra en hilo UI
                self.after(0, lambda exc=exc: self._finish_login(None, exc, progress))
                return
            self.after(0, lambda session=session: self._finish_login(session, None, progress))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_login(self, session, exc: Exception | None, progress: tk.Widget | None) -> None:
        self._login_in_progress = False
        self.configure(cursor="")
        self._hide_login_overlay()
        if exc is not None:
            if isinstance(exc, SupabaseAuthError):
                messagebox.showerror("Login Supabase", str(exc))
            else:
                messagebox.showerror("Login Supabase", f"No se pudo iniciar sesión.\n\n{exc}")
            return
        self._cloud_session = session
        self._rebuild_layout()
        messagebox.showinfo(
            "Login Supabase",
            f"Sesión iniciada correctamente.\n\nUsuario: {session.email}\nRol cloud: {session.role or '(sin rol)'}",
        )

    def _ensure_cloud_session(self) -> bool:
        if self._cloud_session is not None:
            return True
        messagebox.showinfo("Login requerido", "Inicia sesión en Supabase antes de usar esta herramienta.")
        return False

    def _require_admin_session(self) -> bool:
        if not self._ensure_cloud_session():
            return False
        role = (self._cloud_session.role or "").lower()
        if role != "admin":
            messagebox.showwarning(
                "Caja negra cloud",
                "Esta herramienta solo está disponible para usuarios admin.",
            )
            return False
        return True
