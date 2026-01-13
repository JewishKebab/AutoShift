from flask import Blueprint, current_app, jsonify, request
from app.auth.require_user_role import require_user
from app.services.policy_exemptions import (
    list_exemptions_for_assignment,
    create_subscription_exemption,
    build_exemption_name,
    _tomorrow_utc_same_time,
)

bp = Blueprint("policy_exemptions", __name__, url_prefix="/api/policy")

@bp.post("/exemptions/ensure")
@require_user
def ensure_exemption():
    """
    Ensure a subscription-scope exemption exists for POLICY_ASSIGNMENT_ID.
    If any non-expired exemption already exists for the assignment, we skip creation.
    Otherwise we create one that expires ~24h from now.
    """
    payload = request.get_json(silent=True) or {}
    cluster_name = (payload.get("clusterName") or "").strip()
    if not cluster_name:
        return jsonify({"ok": False, "error": "clusterName is required"}), 400

    cfg = current_app.config

    required = [
        "AZURE_TENANT_ID", "SUBSCRIPTION_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"
    ]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        return jsonify({"ok": False, "error": "Missing env vars", "missing": missing}), 400

    policy_assignment_id = cfg.get("POLICY_ASSIGNMENT_ID") or ""
    if not policy_assignment_id:
        return jsonify({"ok": False, "error": "Missing POLICY_ASSIGNMENT_ID"}), 400

    try:
        existing = list_exemptions_for_assignment(
            subscription_id=cfg["SUBSCRIPTION_ID"],
            policy_assignment_id=policy_assignment_id,
            tenant_id=cfg["AZURE_TENANT_ID"],
            client_id=cfg["AZURE_CLIENT_ID"],
            client_secret=cfg["AZURE_CLIENT_SECRET"],
        )

        if existing:
            # Already have an active exemption for that assignment → skip
            return jsonify({
                "ok": True,
                "created": False,
                "exemptionId": existing[0].get("id"),
                "exemptionName": existing[0].get("name"),
            }), 200

        exemption_name = build_exemption_name(cluster_name)
        expires = _tomorrow_utc_same_time()

        created = create_subscription_exemption(
            subscription_id=cfg["SUBSCRIPTION_ID"],
            exemption_name=exemption_name,
            policy_assignment_id=policy_assignment_id,
            expires_on_utc=expires,
            tenant_id=cfg["AZURE_TENANT_ID"],
            client_id=cfg["AZURE_CLIENT_ID"],
            client_secret=cfg["AZURE_CLIENT_SECRET"],
            display_name=f"AutoShift exemption for {cluster_name}",
            description=f"Temporary exemption for cluster deployment. Auto expires.",
            exemption_category="Waiver",
        )

        return jsonify({
            "ok": True,
            "created": True,
            "exemptionId": created.get("id"),
            "exemptionName": created.get("name"),
            "expiresOn": created.get("properties", {}).get("expiresOn"),
        }), 200

    except Exception as e:
        current_app.logger.exception("Ensure policy exemption failed")
        return jsonify({"ok": False, "error": str(e)}), 500
