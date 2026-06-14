from __future__ import annotations

ADMIN_ONLY_MODULES = {
    "security",
    "logs",
    "backups",
    "restore",
    "users",
    "settings",
    "woocommerce_publish",
    "migrations",
}

WORKER_VISIBLE_MODULES = {
    "inventory",
    "price_proposals",
    "cost",
    "cost_pedido",
    "products_read",
}


def can_view_module(role: str, module: str) -> bool:
    role = (role or "standalone").lower()
    if role == "admin":
        return True
    if role == "worker":
        return module in WORKER_VISIBLE_MODULES
    return module not in ADMIN_ONLY_MODULES


def can_execute_operation(role: str, operation: str) -> bool:
    role = (role or "standalone").lower()
    if role == "admin":
        return True
    blocked_for_workers = {
        "restore_backup",
        "view_security_logs",
        "publish_to_woocommerce",
        "sync_from_woocommerce",
        "manage_users",
        "run_migrations",
        "delete_data",
    }
    return operation not in blocked_for_workers
