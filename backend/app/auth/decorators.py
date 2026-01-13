from functools import wraps
from flask import request, current_app, jsonify, g
from .jwt_validator import validate_bearer_token

def require_auth(required_scope: str | None = None, required_role: str | None = None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return jsonify({"ok": False, "error": "Missing Bearer token"}), 401

            token = auth.split(" ", 1)[1].strip()
            tenant_id = current_app.config.get("TENANT_ID")
            audience = current_app.config.get("API_AUDIENCE") or current_app.config.get("API_CLIENT_ID")

            if not tenant_id or not audience:
                return jsonify({"ok": False, "error": "Server auth not configured"}), 500

            try:
                claims = validate_bearer_token(token, tenant_id=tenant_id, audience=audience)
                g.user = claims
            except Exception as e:
                return jsonify({"ok": False, "error": "Invalid token", "details": str(e)}), 401

            # Optional: scope check (scp claim)
            if required_scope:
                scp = (claims.get("scp") or "")
                scopes = set(scp.split())
                if required_scope not in scopes:
                    return jsonify({"ok": False, "error": f"Missing scope: {required_scope}"}), 403

            # Optional: role check (roles claim)
            if required_role:
                roles = claims.get("roles") or []
                if required_role not in roles:
                    return jsonify({"ok": False, "error": f"Missing role: {required_role}"}), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator
