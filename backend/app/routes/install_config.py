from flask import Blueprint, jsonify, request
from app.auth.require_user_role import require_user
from app.services.install_config_builder import build_install_config
from app.services.ssh_vm import ensure_install_config_on_vm


bp = Blueprint("install_config", __name__, url_prefix="/api/install-config")

ALLOWED_VM_SIZES = {"Standard_F8s", "Standard_D4s_v3", "Standard_D8s_v3"}

@bp.post("/push")
@require_user
def push():
    data = request.get_json(silent=True) or {}

    required = [
        "clusterName", "masterCidr", "workerCidr",
        "masterVmSize", "workerVmSize",
        "masterReplicas", "workerReplicas",
    ]
    missing = [k for k in required if data.get(k) in (None, "", [])]
    if missing:
        return jsonify({"ok": False, "error": "Missing fields", "missing": missing}), 400

    cluster_name = str(data["clusterName"]).strip()
    master_cidr = str(data["masterCidr"]).strip()
    worker_cidr = str(data["workerCidr"]).strip()
    master_vm = str(data["masterVmSize"]).strip()
    worker_vm = str(data["workerVmSize"]).strip()

    try:
        master_rep = int(data["masterReplicas"])
        worker_rep = int(data["workerReplicas"])
    except Exception:
        return jsonify({"ok": False, "error": "Replicas must be integers"}), 400

    if master_vm not in ALLOWED_VM_SIZES or worker_vm not in ALLOWED_VM_SIZES:
        return jsonify({"ok": False, "error": "Invalid VM size", "allowed": sorted(ALLOWED_VM_SIZES)}), 400

    # recommended rules for OCP
    if master_rep not in (3, 5):
        return jsonify({"ok": False, "error": "Master replicas must be 3 or 5"}), 400
    if worker_rep < 2 or worker_rep > 6:
        return jsonify({"ok": False, "error": "Worker replicas must be between 2 and 6"}), 400

    yml_text = build_install_config(
        cluster_name=cluster_name,
        master_cidr=master_cidr,
        worker_cidr=worker_cidr,
        master_vm_size=master_vm,
        worker_vm_size=worker_vm,
        master_replicas=master_rep,
        worker_replicas=worker_rep,
    )

    # Your function that creates /home/devops/az-<cluster>-cluster and backup
    ensure_install_config_on_vm(cluster_name=cluster_name, install_config_yaml=yml_text)

    return jsonify({"ok": True}), 200