from flask import Blueprint, jsonify, current_app, request
from app.auth.require_user_role import require_user
from app.services.cluster_discovery import discover_clusters

bp = Blueprint("clusters", __name__, url_prefix="/api/clusters")


@bp.get("")
@require_user
def list_clusters():
    cfg = current_app.config

    cluster_sub = cfg.get("SUBSCRIPTION_ID")
    zone_sub = cfg.get("DNS_ZONE_SUBSCRIPTION_ID") or cluster_sub
    base_domain = cfg.get("BASE_DOMAIN") or "bsmch.net"

    missing = []
    if not cluster_sub:
        missing.append("SUBSCRIPTION_ID")

    if missing:
        return jsonify({"ok": False, "error": "Missing config", "missing": missing}), 400

    debug = (request.args.get("debug") or "").strip().lower() or None

    result = discover_clusters(
        cluster_subscription=cluster_sub,
        zone_subscription=zone_sub,
        base_domain=base_domain,
        debug=debug,
    )

    # debug modes return dict
    if isinstance(result, dict):
        return jsonify({"ok": True, **result}), 200

    # normal mode returns List[Dict]
    return jsonify({"ok": True, "clusters": result}), 200
