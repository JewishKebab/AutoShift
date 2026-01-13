from functools import wraps
from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt

REQUIRED_ROLE = "User"  # must match Entra App Role VALUE exactly

def require_user(fn):
    """
    Requires:
      - valid JWT (from cookies)
      - user has REQUIRED_ROLE inside 'azure_roles' claim
    """
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        token = get_jwt()
        azure_roles = token.get("azure_roles") or []

        if REQUIRED_ROLE not in azure_roles:
            return jsonify({"ok": False, "error": "Forbidden: missing User role"}), 403

        return fn(*args, **kwargs)

    return wrapper
