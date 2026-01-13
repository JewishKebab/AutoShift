from flask import Blueprint, jsonify, request
from app.auth.require_user_role import require_user
from app.services.destroy_runner import start_destroy_job

bp = Blueprint("clusters_destroy", __name__, url_prefix="/api/clusters")


@bp.post("/destroy")
@require_user
def destroy():
    data = request.get_json(silent=True) or {}
    cluster_name = (data.get("clusterName") or "").strip()
    if not cluster_name:
        return jsonify({"ok": False, "error": "clusterName is required"}), 400

    job = start_destroy_job(cluster_name)
    return jsonify({"ok": True, "jobId": job.id}), 200
