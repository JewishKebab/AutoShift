from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt

bp = Blueprint("identity", __name__, url_prefix="/api")

@bp.get("/identity")
@jwt_required()
def identity():
    t = get_jwt()
    return jsonify({
        "name": t.get("name"),
        "email": t.get("email"),
        "role": t.get("role"),
        "azure_roles": t.get("azure_roles", []),
    }), 200
