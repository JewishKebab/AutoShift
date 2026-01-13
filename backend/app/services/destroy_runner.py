# app/services/destroy_runner.py
import os
import re
import threading
import time
import uuid
import paramiko
from typing import Tuple, Optional

from app.services.installer_runner import Job, _jobs  # reuse job store
from app.services.installer_vm import ensure_installer_vm_ready
from app.services.key_vault import delete_kubeadmin_password

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")  # strips terminal color codes


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def start_destroy_job(cluster_name: str) -> Job:
    job_id = str(uuid.uuid4())
    job = Job(id=job_id)
    _jobs[job_id] = job  # reuse /api/installer/logs + /api/installer/stream

    t = threading.Thread(target=_run_destroy, args=(job, cluster_name), daemon=True)
    t.start()
    return job


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _normalize_to_folder_name(input_name: str) -> str:
    """
    Accepts many forms and returns canonical folder:
      az-<base>-openshift-cluster

    Handles inputs like:
      testing45
      testing45-openshift
      testing45-openshift-o
      az-testing45-openshift-cluster
      az-testing45-openshift-o-cluster
      az-testing45-cluster
    """
    s = (input_name or "").strip()

    # If user passed the full folder already, strip leading base path if any
    s = s.replace("\\", "/")
    if "/" in s:
        s = s.split("/")[-1].strip()

    # Remove leading az-
    if s.startswith("az-"):
        s = s[len("az-") :]

    # Remove trailing "-cluster" (generic)
    if s.endswith("-cluster"):
        s = s[: -len("-cluster")]

    # Remove trailing "-openshift" (if present)
    if s.endswith("-openshift"):
        s = s[: -len("-openshift")]

    # Remove trailing "-openshift-o" / "-o" mistakes
    if s.endswith("-openshift-o"):
        s = s[: -len("-openshift-o")]
    if s.endswith("-o"):
        s = s[: -len("-o")]

    # Collapse accidental doubles like "...-openshift-openshift"
    while s.endswith("-openshift-openshift"):
        s = s[: -len("-openshift")]

    base = s.strip("-") or "cluster"
    return f"az-{base}-openshift-cluster"


def _exec(ssh: paramiko.SSHClient, cmd: str, *, timeout: int = 60) -> Tuple[int, str, str]:
    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=False, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="ignore")
    err = stderr.read().decode("utf-8", errors="ignore")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def _run_destroy(job: Job, cluster_name: str) -> None:
    host = os.environ["INSTALLER_VM_HOST"]
    user = os.environ.get("INSTALLER_VM_USER", "asgard")
    ssh_password = os.environ["INSTALLER_VM_PASSWORD"]  # only for SSH login

    base_dir = os.environ.get("INSTALLER_BASE_DIR", "/home/devops")
    installer_path = os.environ.get("INSTALLER_OPENSHIFT_INSTALL_PATH", "/home/devops/openshift-install")

    folder = _normalize_to_folder_name(cluster_name)
    full_dir = f"{base_dir.rstrip('/')}/{folder}"

    # Ensure VM ready (power + TCP)
    try:
        job.append("[destroy] ensuring installer VM ready (power + TCP)")
        ensure_installer_vm_ready(
            host=host,
            power_timeout_seconds=int(os.environ.get("VM_START_TIMEOUT_SECONDS", "900")),
            ssh_timeout_seconds=int(os.environ.get("SSH_WAIT_TIMEOUT_SECONDS", "900")),
        )
        job.append("[destroy] installer VM ready")
    except Exception as e:
        job.error = str(e)
        job.done = True
        job.append(f"[error] installer VM not ready: {e}")
        return

    cmd = f"cd {base_dir} && {installer_path} destroy cluster --dir {folder} --log-level debug"
    job.append(f"$ {cmd}")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname=host,
            username=user,
            password=ssh_password,
            look_for_keys=False,
            allow_agent=False,
            timeout=20,
            banner_timeout=60,
            auth_timeout=60,
        )

        # Require NOPASSWD sudo so we NEVER send a password into a PTY
        rc, _, err = _exec(ssh, "sudo -n true", timeout=20)
        if rc != 0:
            raise RuntimeError(
                f"Installer VM sudo is not NOPASSWD (sudo -n true failed): {(err or '').strip()}"
            )

        # If folder is missing, tell the user and stop (your requirement)
        rc, _, _ = _exec(ssh, f"sudo -n test -d {_sh_quote(full_dir)}", timeout=20)
        if rc != 0:
            job.error = f"Cluster folder not found on installer VM: {full_dir}"
            job.done = True
            job.append(f"[error] {job.error}")
            return

        # Stream logs with PTY (good streaming) but sudo -n (no password)
        sudo_cmd = f"sudo -n bash -lc {_sh_quote(cmd)}"
        _, stdout, stderr = ssh.exec_command(sudo_cmd, get_pty=True)

        for raw in iter(stdout.readline, ""):
            if not raw:
                break
            job.append(strip_ansi(raw.rstrip("\n")))

        for raw in iter(stderr.readline, ""):
            if not raw:
                break
            job.append(strip_ansi(raw.rstrip("\n")))

        rc = stdout.channel.recv_exit_status()
        job.exit_code = rc
        job.append(f"[done] exit_code={rc}")

        if rc != 0:
            job.error = f"destroy failed (exit_code={rc})"
            job.done = True
            return

        # After successful destroy, remove the cluster folder
        job.append(f"[destroy] removing cluster folder: {full_dir}")
        rc2, out2, err2 = _exec(ssh, f"sudo -n rm -rf {_sh_quote(full_dir)}", timeout=180)
        if rc2 != 0:
            job.append(f"[destroy][warn] failed to remove folder: {(err2 or out2).strip()}")
        else:
            job.append("[destroy] folder removed ✅")

        # Delete only THIS cluster's kubeadmin secret (best-effort)
        try:
            job.append("[kv] deleting kubeadmin password secret...")
            deleted = delete_kubeadmin_password(cluster_name=cluster_name)
            if deleted:
                job.append("[kv] secret deleted")
            else:
                job.append("[kv] secret not found (nothing to delete)")
        except Exception as e:
            job.append(f"[kv][warn] failed to delete secret: {e}")

        job.done = True
        job.append("[done] destroy completed ✅")

    except Exception as e:
        job.error = str(e)
        job.done = True
        job.append(f"[error] {e}")
    finally:
        try:
            ssh.close()
        except Exception:
            pass
