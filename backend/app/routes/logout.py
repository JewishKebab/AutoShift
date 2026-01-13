from flask import Blueprint, jsonify
from flask_jwt_extended import unset_jwt_cookies

bp = Blueprint("logout", __name__, url_prefix="/api")

@bp.post("/logout")
def logout():
    resp = jsonify({"ok": True})
    unset_jwt_cookies(resp)  # clears access_token_cookie + refresh_token_cookie (+ csrf cookies if enabled)
    return resp, 200
