from functools import wraps
from flask import abort
from flask_login import current_user
from .models import WorkerRole, Role  # заміни на свій шлях імпорту

def role_required(*allowed_roles):
    """
    Використання:
        @role_required('admin', 'manager')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(403)

            # Отримуємо активні ролі користувача
            active_roles = (
                WorkerRole.query
                .join(Role, WorkerRole.role_id == Role.role_id)
                .filter(
                    WorkerRole.worker_id == current_user.worker_id,
                    WorkerRole.status == 'active'
                )
                .with_entities(Role.name)
                .all()
            )
            active_role_names = [r.name.lower() for r in active_roles]

            # Якщо користувач не має жодної дозволеної ролі
            if not any(role.lower() in active_role_names for role in allowed_roles):
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator
