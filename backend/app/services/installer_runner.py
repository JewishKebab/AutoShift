# app/services/installer_runner.py
import os
import re
import threading
import uuid
import time
import paramiko
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple

from app.services.private_dns_links import link_private_dns_zone_to_hubs
from app.services.key_vault import store_kubeadmin_password

MAX_LOG_LINES = 20000  # keep last N lines per job (in memory)

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")  # strips terminal color codes


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


@dataclass
class Job:
    id: str
    done: bool = False
    exit_code: Optional[int] = None
    error: Optional[str] = None

    seq: int = 0
    lines: List[Tuple[int, str]] = field(default_factory=list)
    cond: threading.Condition = field(default_factory=threading.Condition)

    dns_started: bool = False
    dns_lock: threading.Lock = field(default_factory=threading.Lock)

    kv_saved: bool = False
    kv_lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, line: str) -> int:
        with self.cond:
            self.seq += 1
            s = self.seq
            self.lines.append((s, line))
            if len(self.lines) > MAX_LOG_LINES:
                self.lines = self.lines[-MAX_LOG_LINES:]
            self.cond.notify_all()
            return s


_jobs: Dict[str, Job] = {}


def start_install_job(cluster_name: str) -> Job:
    job_id = str(uuid.uuid4())
    job = Job(id=job_id)
    _jobs[job_id] = job
    threading.Thread(target=_run_install, args=(job, cluster_name), daemon=True).start()
    return job


def get_job(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _start_dns_watcher_if_needed(job: Job, cluster_name: str, reason: str) -> None:
    with job.dns_lock:
        if job.dns_started:
            return
        job.dns_started = True

    def _dns_worker():
        try:
            job.append(f"[dns] watcher started ({reason})")
            link_private_dns_zone_to_hubs(cluster_name=cluster_name, log=job.append)
            job.append("[dns] watcher finished")
        except Exception as e:
            job.append(f"[dns][error] {e}")

    threading.Thread(target=_dns_worker, daemon=True).start()


def _normalize_cluster_name(name: str) -> str:
    """
    Your UI sometimes passes cluster_name like 'testing44-openshift'.
    We normalize to a base name so we don't generate:
      az-testing44-openshift-openshift-cluster
    """
    s = (name or "").strip()

    # If someone accidentally double-suffixed, collapse it.
    while s.endswith("-openshift-openshift"):
        s = s[: -len("-openshift")]

    # Strip exactly one '-openshift' suffix
    if s.endswith("-openshift"):
        s = s[: -len("-openshift")]

    return s.strip("-") or "cluster"


def _cluster_dir_name(raw_cluster_name: str) -> str:
    """
    Canonical convention: az-<base>-openshift-cluster
    """
    base = _normalize_cluster_name(raw_cluster_name)
    return f"az-{base}-openshift-cluster"


def _exec(ssh: paramiko.SSHClient, cmd: str, *, timeout: int = 60) -> Tuple[int, str, str]:
    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=False, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="ignore")
    err = stderr.read().decode("utf-8", errors="ignore")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def _read_remote_file_sudo_nopass(ssh: paramiko.SSHClient, remote_path: str) -> str:
    cmd = f"sudo -n cat {_sh_quote(remote_path)}"
    rc, out, err = _exec(ssh, cmd, timeout=30)
    if rc != 0:
        raise RuntimeError(f"cat failed rc={rc}: {(err or out).strip()}")
    return out


def _store_kubeadmin_password_from_file(
    job: Job,
    *,
    ssh: paramiko.SSHClient,
    cluster_name: str,
    base_dir: str,
    cluster_dir: str,
) -> None:
    with job.kv_lock:
        if job.kv_saved:
            return

    wait_seconds = int(os.environ.get("KV_PASSWORD_FILE_WAIT_SECONDS", "120"))
    deadline = time.time() + wait_seconds
    last_err: Optional[BaseException] = None

    remote_path = f"{base_dir.rstrip('/')}/{cluster_dir}/auth/kubeadmin-password"
    job.append(f"[kv] reading kubeadmin password from file: {remote_path} (wait up to {wait_seconds}s)")

    while time.time() < deadline:
        try:
            content = _read_remote_file_sudo_nopass(ssh, remote_path)
            pw = (content or "").strip().splitlines()[0].strip()
            if not pw:
                raise RuntimeError("kubeadmin-password file is empty")

            secret_id = store_kubeadmin_password(cluster_name=cluster_name, password=pw)
            with job.kv_lock:
                job.kv_saved = True
            job.append(f"[kv] kubeadmin password saved to Key Vault. secretId={secret_id}")
            return
        except Exception as e:
            last_err = e
            job.append(f"[kv][info] waiting for kubeadmin-password file... ({type(e).__name__}: {e})")
            time.sleep(5)

    job.append(f"[kv][error] failed to store kubeadmin password from file (last error: {last_err})")


def _run_install(job: Job, cluster_name: str) -> None:
    host = os.environ["INSTALLER_VM_HOST"]
    user = os.environ.get("INSTALLER_VM_USER", "asgard")
    ssh_password = os.environ["INSTALLER_VM_PASSWORD"]  # only for SSH login

    base_dir = os.environ.get("INSTALLER_BASE_DIR", "/home/devops")
    installer_path = os.environ.get("INSTALLER_OPENSHIFT_INSTALL_PATH", "/home/devops/openshift-install")

    dir_name = _cluster_dir_name(cluster_name)
    install_cfg = f"{base_dir.rstrip('/')}/{dir_name}/install-config.yaml"

    cmd = f"cd {base_dir} && {installer_path} create cluster --dir {dir_name} --log-level debug"
    job.append(f"$ {cmd}")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    trigger_phrase = "Network infrastructure is ready"

    try:
        ssh.connect(
            hostname=host,
            username=user,
            password=ssh_password,
            look_for_keys=False,
            allow_agent=False,
            timeout=15,
        )

        # ensure sudo is NOPASSWD (prevents the whole password-echo/typing problem)
        rc, _, err = _exec(ssh, "sudo -n true", timeout=20)
        if rc != 0:
            raise RuntimeError(f"Installer VM sudo is not NOPASSWD (sudo -n true failed): {(err or '').strip()}")

        # fail fast if install-config doesn't exist -> avoids interactive wizard
        rc, _, _ = _exec(ssh, f"sudo -n test -f {_sh_quote(install_cfg)}", timeout=20)
        if rc != 0:
            raise RuntimeError(
                f"Missing install-config.yaml on installer VM at {install_cfg}. "
                f"Push install-config first (or ensure naming matches)."
            )

        # stream logs with PTY, but no password is ever sent (sudo -n)
        sudo_cmd = f"sudo -n bash -lc {_sh_quote(cmd)}"
        _, stdout, stderr = ssh.exec_command(sudo_cmd, get_pty=True)

        for raw in iter(stdout.readline, ""):
            if not raw:
                break
            plain = strip_ansi(raw.rstrip("\n"))
            job.append(plain)

            if trigger_phrase in plain:
                _start_dns_watcher_if_needed(job, cluster_name, reason=f"triggered by '{trigger_phrase}'")

        for raw in iter(stderr.readline, ""):
            if not raw:
                break
            plain = strip_ansi(raw.rstrip("\n"))
            job.append(plain)

        rc = stdout.channel.recv_exit_status()
        job.exit_code = rc
        job.done = True
        job.append(f"[done] exit_code={rc}")

        if rc == 0:
            _store_kubeadmin_password_from_file(
                job,
                ssh=ssh,
                cluster_name=cluster_name,
                base_dir=base_dir,
                cluster_dir=dir_name,
            )

        _start_dns_watcher_if_needed(job, cluster_name, reason="fallback at install end")

    except Exception as e:
        job.error = str(e)
        job.done = True
        job.append(f"[error] {e}")
        _start_dns_watcher_if_needed(job, cluster_name, reason="fallback after installer error")

    finally:
        try:
            ssh.close()
        except Exception:
            pass
