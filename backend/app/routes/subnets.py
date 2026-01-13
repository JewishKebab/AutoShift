from flask import Blueprint, current_app, jsonify, request
from app.azure_client import get_network_client
from app.services.subnet_allocator import suggest_next_pair
from app.auth.require_user_role import require_user

bp = Blueprint("subnets", __name__, url_prefix="/api/subnets")


@bp.get("/suggest")
@require_user
def suggest():
    """
    Query Azure for existing subnets in the configured VNet, then return the next free /22 + /22 pair.
    Also ensures subnet names do NOT already exist to avoid collisions.
    """
    cluster_name = (request.args.get("clusterName") or "").strip()
    if not cluster_name:
        return jsonify({"ok": False, "error": "clusterName is required"}), 400

    cfg = current_app.config

    required = [
        "AZURE_TENANT_ID",
        "SUBSCRIPTION_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "AZ_RESOURCE_GROUP",
        "AZ_VNET_NAME",
    ]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        return jsonify({"ok": False, "error": "Missing env vars", "missing": missing}), 400

    base_prefix = cfg.get("AZ_SUBNET_PREFIX") or "10.104"

    try:
        client = get_network_client(
            tenant_id=cfg["AZURE_TENANT_ID"],
            client_id=cfg["AZURE_CLIENT_ID"],
            client_secret=cfg["AZURE_CLIENT_SECRET"],
            subscription_id=cfg["SUBSCRIPTION_ID"],
        )

        subnets = list(client.subnets.list(cfg["AZ_RESOURCE_GROUP"], cfg["AZ_VNET_NAME"]))

        # ---- prevent subnet name collisions ----
        existing_names = {s.name.lower() for s in subnets if s.name}
        master_name = f"{cluster_name}-master-subnet".lower()
        worker_name = f"{cluster_name}-worker-subnet".lower()

        conflicts = []
        if master_name in existing_names:
            conflicts.append(f"{cluster_name}-master-subnet")
        if worker_name in existing_names:
            conflicts.append(f"{cluster_name}-worker-subnet")

        if conflicts:
            return jsonify({"ok": False, "error": "Subnet name already exists", "conflicts": conflicts}), 409

        # ---- collect existing CIDR prefixes ----
        existing_prefixes: list[str] = []
        for s in subnets:
            if getattr(s, "address_prefix", None):
                existing_prefixes.append(s.address_prefix)
            if getattr(s, "address_prefixes", None):
                existing_prefixes.extend([p for p in (s.address_prefixes or []) if p])

        suggestion = suggest_next_pair(existing_prefixes, base_prefix=base_prefix)

        return jsonify({
            "ok": True,
            "vnet": cfg["AZ_VNET_NAME"],
            "master": f"{cluster_name}-master-subnet",
            "worker": f"{cluster_name}-worker-subnet",
            "masterCidr": suggestion.master_cidr,
            "workerCidr": suggestion.worker_cidr,
        }), 200

    except Exception as e:
        current_app.logger.exception("Subnet suggest failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/create")
@require_user
def create():
    """
    Create the suggested master+worker subnets in the configured VNet.

    Idempotent behavior:
    - If subnet exists with same CIDR -> ok, created=false for that subnet
    - If subnet exists with different CIDR -> 409 (conflict)
    - If subnet doesn't exist -> create it
    """
    payload = request.get_json(silent=True) or {}
    cluster_name = (payload.get("clusterName") or "").strip()
    master_cidr = (payload.get("masterCidr") or "").strip()
    worker_cidr = (payload.get("workerCidr") or "").strip()

    if not cluster_name:
        return jsonify({"ok": False, "error": "clusterName is required"}), 400
    if not master_cidr or not worker_cidr:
        return jsonify({"ok": False, "error": "masterCidr and workerCidr are required"}), 400

    master_name = f"{cluster_name}-master-subnet"
    worker_name = f"{cluster_name}-worker-subnet"

    cfg = current_app.config
    required = [
        "AZURE_TENANT_ID",
        "SUBSCRIPTION_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "AZ_RESOURCE_GROUP",
        "AZ_VNET_NAME",
    ]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        return jsonify({"ok": False, "error": "Missing env vars", "missing": missing}), 400

    try:
        client = get_network_client(
            tenant_id=cfg["AZURE_TENANT_ID"],
            client_id=cfg["AZURE_CLIENT_ID"],
            client_secret=cfg["AZURE_CLIENT_SECRET"],
            subscription_id=cfg["SUBSCRIPTION_ID"],
        )

        # Existing subnets
        subnets = list(client.subnets.list(cfg["AZ_RESOURCE_GROUP"], cfg["AZ_VNET_NAME"]))
        by_name = {s.name.lower(): s for s in subnets if s.name}

        results = {
            "master": {"name": master_name, "cidr": master_cidr, "created": False, "id": None},
            "worker": {"name": worker_name, "cidr": worker_cidr, "created": False, "id": None},
        }

        def ensure_one(name: str, cidr: str, key: str):
            existing = by_name.get(name.lower())
            if existing:
                existing_cidr = getattr(existing, "address_prefix", None) or ""
                # Some subnets store multiple prefixes
                if not existing_cidr and getattr(existing, "address_prefixes", None):
                    prefixes = existing.address_prefixes or []
                    existing_cidr = prefixes[0] if prefixes else ""

                if existing_cidr and existing_cidr != cidr:
                    return ("conflict", existing.id, existing_cidr)

                results[key]["created"] = False
                results[key]["id"] = existing.id
                return ("ok", existing.id, existing_cidr or cidr)

            # Create subnet
            poller = client.subnets.begin_create_or_update(
                cfg["AZ_RESOURCE_GROUP"],
                cfg["AZ_VNET_NAME"],
                name,
                {"address_prefix": cidr},
            )
            created = poller.result()

            results[key]["created"] = True
            results[key]["id"] = created.id
            return ("created", created.id, cidr)

        # Ensure master then worker
        status_m, id_m, cidr_m = ensure_one(master_name, master_cidr, "master")
        if status_m == "conflict":
            return jsonify({
                "ok": False,
                "error": "Subnet already exists with different CIDR",
                "subnet": master_name,
                "existingCidr": cidr_m,
                "requestedCidr": master_cidr,
                "subnetId": id_m,
            }), 409

        status_w, id_w, cidr_w = ensure_one(worker_name, worker_cidr, "worker")
        if status_w == "conflict":
            return jsonify({
                "ok": False,
                "error": "Subnet already exists with different CIDR",
                "subnet": worker_name,
                "existingCidr": cidr_w,
                "requestedCidr": worker_cidr,
                "subnetId": id_w,
            }), 409

        return jsonify({
            "ok": True,
            "vnet": cfg["AZ_VNET_NAME"],
            "resourceGroup": cfg["AZ_RESOURCE_GROUP"],
            "master": results["master"],
            "worker": results["worker"],
        }), 200

    except Exception as e:
        current_app.logger.exception("Subnet create failed")
        return jsonify({"ok": False, "error": str(e)}), 500
