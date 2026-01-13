# app/routes/installer.py
from flask import Blueprint, jsonify, request, Response
from app.auth.require_user_role import require_user
from app.services.installer_runner import start_install_job, get_job
import time

bp = Blueprint("installer", __name__, url_prefix="/api/installer")


@bp.post("/start")
@require_user
def start():
    data = request.get_json(silent=True) or {}
    cluster_name = (data.get("clusterName") or "").strip()
    if not cluster_name:
        return jsonify({"ok": False, "error": "clusterName is required"}), 400

    # ✅ start_install_job() puts the job in the dict BEFORE starting the thread
    job = start_install_job(cluster_name)

    return jsonify({"ok": True, "jobId": job.id}), 200


@bp.get("/status/<job_id>")
@require_user
def status(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "job not found"}), 404

    return jsonify(
        {
            "ok": True,
            "done": job.done,
            "exitCode": job.exit_code,
            "error": job.error,
            "lastSeq": job.seq,
        }
    ), 200


@bp.get("/logs/<job_id>")
@require_user
def logs(job_id: str):
    job = get_job(job_id)

    # ✅ Don't 404: UI can safely poll until job exists
    from_seq = int(request.args.get("from", "0") or "0")
    if not job:
        return jsonify(
            {
                "ok": True,
                "done": False,
                "exitCode": None,
                "error": None,
                "lastSeq": from_seq,
                "lines": [],
            }
        ), 200

    with job.cond:
        chunk = [(s, line) for (s, line) in job.lines if s > from_seq]

    return jsonify(
        {
            "ok": True,
            "done": job.done,
            "exitCode": job.exit_code,
            "error": job.error,
            "lastSeq": job.seq,
            "lines": chunk,
        }
    ), 200


@bp.get("/stream/<job_id>")
@require_user
def stream(job_id: str):
    job = get_job(job_id)

    # Support either ?from=123 OR SSE auto-reconnect Last-Event-ID header
    from_qs = request.args.get("from")
    last_event_id = request.headers.get("Last-Event-ID")
    cursor = int(from_qs or last_event_id or 0)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # helpful for nginx/proxies
        "Connection": "keep-alive",
    }

    # ✅ Don't 404 here either. Return an SSE stream with heartbeats.
    if not job:
        def empty_stream():
            for _ in range(10):
                yield ":\n\n"
                time.sleep(0.5)

        return Response(empty_stream(), mimetype="text/event-stream", headers=headers)

    def event_stream():
        nonlocal cursor

        while True:
            with job.cond:
                new_lines = [(s, l) for (s, l) in job.lines if s > cursor]
                if not new_lines:
                    if job.done:
                        break
                    job.cond.wait(timeout=1.0)
                    yield ":\n\n"  # heartbeat
                    continue

            for s, line in new_lines:
                cursor = s
                yield f"id: {s}\n"
                yield f"data: {line}\n\n"

        yield f"id: {job.seq}\n"
        yield "data: [done]\n\n"

    return Response(event_stream(), mimetype="text/event-stream", headers=headers)
