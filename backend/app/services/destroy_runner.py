# app/services/destroy_runner.py
import os
import re
import threading
import uuid
import time
import paramiko
from typing import Tuple, Optional

from azure.identity import ClientSecretCredential
from azure.mgmt.network import NetworkManagementClient
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError

from app.services.installer_runner import Job, _jobs  # reuse job store
from app.services.installer_vm import ensure_installer_vm_ready
from app.services.key_vault import delete_kubeadmin_password

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")  # strips terminal color codes


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def start_destroy_job(cluster_name: str) -> Job:
    job_id = str(uuid.uuid4())
    base = _normalize_to_base_name(cluster_name)

    job = Job(id=job_id, cluster_name=base)
    _jobs[job_id] = job

    t = threading.Thread(target=_run_destroy, args=(job, base), daemon=True)
    t.start()
    return job


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _normalize_to_base_name(input_name: str) -> str:
    s = (input_name or "").strip()
    s = s.replace("\\", "/")
    if "/" in s:
        s = s.split("/")[-1].strip()

    if s.startswith("az-"):
        s = s[len("az-") :]

    if s.endswith("-cluster"):
        s = s[: -len("-cluster")]

    while s.endswith("-openshift-openshift"):
        s = s[: -len("-openshift")]

    if s.endswith("-openshift-o"):
        s = s[: -len("-openshift-o")]
    if s.endswith("-openshift"):
        s = s[: -len("-openshift")]
    if s.endswith("-o"):
        s = s[: -len("-o")]

    # remove "openshift" token anywhere
    parts = [p for p in s.split("-") if p and p.lower() != "openshift"]
    s = "-".join(parts)

    return s.strip("-") or "cluster"


def _folder_name_from_base(base: str) -> str:
    return f"az-{base}-cluster"


def _exec(ssh: paramiko.SSHClient, cmd: str, *, timeout: int = 60) -> Tuple[int, str, str]:
    _, stdout, stderr = ssh.exec_command(cmd, get_pty=False, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="ignore")
    err = stderr.read().decode("utf-8", errors="ignore")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


# ------------------------
# Azure subnet deletion
# ------------------------

_cred: Optional[ClientSecretCredential] = None
_net_client: Optional[NetworkManagementClient] = None


def _get_credential() -> ClientSecretCredential:
    global _cred
    if _cred:
        return _cred
    _cred = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
    return _cred


def _network_client() -> NetworkManagementClient:
    global _net_client
    if _net_client:
        return _net_client
    # If your network subscription differs, add env var OCP_NETWORK_SUBSCRIPTION_ID and use it here.
    sub_id = os.environ.get("OCP_NETWORK_SUBSCRIPTION_ID") or os.environ["SUBSCRIPTION_ID"]
    _net_client = NetworkManagementClient(_get_credential(), sub_id)
    return _net_client


def _delete_subnet(job: Job, *, network_rg: str, vnet_name: str, subnet_name: str) -> None:
    net = _network_client()
    try:
        job.append(f"[net] deleting subnet: {network_rg}/{vnet_name}/{subnet_name}")
        poller = net.subnets.begin_delete(network_rg, vnet_name, subnet_name)
        poller.result()
        job.append(f"[net] deleted subnet: {subnet_name}")
    except ResourceNotFoundError:
        job.append(f"[net][warn] subnet not found (already gone): {subnet_name}")
    except HttpResponseError as e:
        job.append(f"[net][warn] failed deleting subnet {subnet_name}: {e}")


def _delete_cluster_subnets(job: Job, cluster_base: str) -> None:
    network_rg = os.environ["OCP_NETWORK_RG"]
    vnet_name = os.environ["OCP_VNET_NAME"]

    # Your install-config uses:
    # controlPlaneSubnet: f"{cluster_name}-master-subnet"
    # computeSubnet: f"{cluster_name}-worker-subnet"
    master_subnet = f"{cluster_base}-master-subnet"
    worker_subnet = f"{cluster_base}-worker-subnet"

    _delete_subnet(job, network_rg=network_rg, vnet_name=vnet_name, subnet_name=master_subnet)
    _delete_subnet(job, network_rg=network_rg, vnet_name=vnet_name, subnet_name=worker_subnet)


def _run_destroy(job: Job, cluster_base: str) -> None:
    host = os.environ["INSTALLER_VM_HOST"]
    user = os.environ.get("INSTALLER_VM_USER", "asgard")
    ssh_password = os.environ["INSTALLER_VM_PASSWORD"]

    base_dir = os.environ.get("INSTALLER_BASE_DIR", "/home/devops")
    installer_path = os.environ.get("INSTALLER_OPENSHIFT_INSTALL_PATH", "/home/devops/openshift-install")

    folder = _folder_name_from_base(cluster_base)
    full_dir = f"{base_dir.rstrip('/')}/{folder}"

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

        rc, _, err = _exec(ssh, "sudo -n true", timeout=20)
        if rc != 0:
            raise RuntimeError(f"Installer VM sudo is not NOPASSWD (sudo -n true failed): {(err or '').strip()}")

        rc, _, _ = _exec(ssh, f"sudo -n test -d {_sh_quote(full_dir)}", timeout=20)
        if rc != 0:
            job.error = f"Cluster folder not found on installer VM: {full_dir}"
            job.done = True
            job.append(f"[error] {job.error}")
            return

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

        # remove folder
        job.append(f"[destroy] removing cluster folder: {full_dir}")
        rc2, out2, err2 = _exec(ssh, f"sudo -n rm -rf {_sh_quote(full_dir)}", timeout=180)
        if rc2 != 0:
            job.append(f"[destroy][warn] failed to remove folder: {(err2 or out2).strip()}")
        else:
            job.append("[destroy] folder removed")

        # delete kubeadmin secret (best-effort)
        try:
            job.append("[kv] deleting kubeadmin password secret...")
            delete_kubeadmin_password(cluster_name=cluster_base)
            job.append("[kv] secret delete requested")
        except Exception as e:
            job.append(f"[kv][warn] failed to delete secret: {e}")

        # delete subnets (best-effort)
        try:
            job.append("[net] deleting cluster subnets...")
            _delete_cluster_subnets(job, cluster_base)
            job.append("[net] subnet deletion finished")
        except Exception as e:
            job.append(f"[net][warn] subnet deletion step failed: {e}")

        job.done = True
        job.append("[done] destroy completed")

    except Exception as       e:
        job.error = str(e)
        job.done = True
        job.append(f"[error] {e}")
    finally:
        try:
            ssh.close()
        except Exception:
            pass
