"""Backend permission checks. Never rely on hidden UI controls for security."""
from .authentication import current_role


def require_role(user_id, allowed_roles):
    role = current_role(user_id)
    if role not in set(allowed_roles):
        raise PermissionError("You do not have permission to perform this action.")
    return role


def require_admin(user_id):
    return require_role(user_id, {"ADMIN", "MAIN_ADMIN"})


def require_main_admin(user_id):
    return require_role(user_id, {"MAIN_ADMIN"})
