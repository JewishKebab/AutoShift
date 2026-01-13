# app/services/ssh_vm.py
import os
import time
import socket
from typing import Optional

import paramiko
from paramiko.ssh_exception import (
    SSHException,
    NoValidConnectionsError,
    AuthenticationException,
)

from app.services.installer_vm import ensure_installer_vm_ready


def _log(msg: str) -> None:
    print(f"[ssh-vm] {msg}", flush=True)


def _probe_ssh_ready(client: paramiko.SSHClient) -> None:
    _log("Probe: shell")
    _, stdout, stderr = client.exec_command("echo __ok__", timeout=20)
    out = stdout.read().decode("utf-8", errors="ignore").strip()
    err = stderr.read().decode("utf-8", errors="ignore").strip()
    if "__ok__" not in out:
        raise RuntimeError(f"SSH shell probe failed: out={out!r} err={err!r}")

    _log("Probe: sudo -n true")
    _, stdout, stderr = client.exec_command("sudo -n true", timeout=20)
    _ = stdout.read()
    err = stderr.read().decode("utf-8", errors="ignore").strip()
    code = stdout.channel.recv_exit_status()
    if code != 0:
        raise RuntimeError(f"Sudo probe failed: {err or 'sudo returned non-zero'}")


def _connect() -> paramiko.SSHClient:
    host = os.environ["INSTALLER_VM_HOST"]
    user = os.environ.get("INSTALLER_VM_USER", "asgard")
    password = os.environ["INSTALLER_VM_PASSWORD"]

    info = ensure_installer_vm_ready(
        host=host,
        power_timeout_seconds=int(os.environ.get("VM_START_TIMEOUT_SECONDS", "900")),
        ssh_timeout_seconds=int(os.environ.get("SSH_WAIT_TIMEOUT_SECONDS", "900")),
    )

    action = str(info.get("action", "none"))

    #  Retry window (seconds)
    # - normal: 5 minutes
    # - if VM was down and we started it: 15 minutes
    retry_seconds = int(os.environ.get("SSH_CONNECT_RETRY_SECONDS", "300"))
    if action.startswith("started-from-"):
        retry_seconds = max(retry_seconds, 900)

    deadline = time.time() + retry_seconds
    attempt = 0
    last_err: Optional[BaseException] = None

    # per-attempt timeouts (tunable)
    connect_timeout = int(os.environ.get("SSH_CONNECT_TIMEOUT", "20"))
    banner_timeout = int(os.environ.get("SSH_BANNER_TIMEOUT", "60"))
    auth_timeout = int(os.environ.get("SSH_AUTH_TIMEOUT", "60"))

    while time.time() < deadline:
        attempt += 1
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            _log(f"Attempt #{attempt}: connecting to {user}@{host} ...")
            client.connect(
                hostname=host,
                username=user,
                password=password,
                timeout=connect_timeout,
                banner_timeout=banner_timeout,
                auth_timeout=auth_timeout,
                look_for_keys=False,
                allow_agent=False,
            )

            # keepalive helps avoid weird hangs mid-session
            tr = client.get_transport()
            if tr:
                tr.set_keepalive(30)

            _probe_ssh_ready(client)
            _log("SSH usable")
            return client

        except AuthenticationException as e:
            raise RuntimeError(f"SSH auth failed for {user}@{host}: {e}") from e

        except (NoValidConnectionsError, SSHException, socket.timeout, OSError, RuntimeError, TimeoutError) as e:
            last_err = e
            _log(f"Attempt #{attempt} failed: {type(e).__name__}: {e}")
            try:
                client.close()
            except Exception:
                pass
            time.sleep(5)

        except Exception as e:
            last_err = e
            _log(f"Attempt #{attempt} unexpected: {type(e).__name__}: {e}")
            try:
                client.close()
            except Exception:
                pass
            time.sleep(5)

    raise RuntimeError(
        f"SSH connect/probe failed after {attempt} attempts over ~{retry_seconds}s. "
        f"Host={host} user={user}. Last error: {type(last_err).__name__}: {last_err}"
    )


def quote_bash(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def run_sudo(client: paramiko.SSHClient, command: str) -> str:
    _, stdout, stderr = client.exec_command(f"sudo -n bash -lc {quote_bash(command)}")
    out = stdout.read().decode("utf-8", errors="ignore")
    err = stderr.read().decode("utf-8", errors="ignore")
    if stdout.channel.recv_exit_status() != 0:
        raise RuntimeError(f"Command failed: {command}\n{err or out}")
    return out


def _exec(client: paramiko.SSHClient, cmd: str) -> None:
    _, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="ignore")
    err = stderr.read().decode("utf-8", errors="ignore")
    code = stdout.channel.recv_exit_status()
    if code != 0:
        raise RuntimeError(f"Command failed ({code}): {cmd}\n{err or out}")


def ensure_install_config_on_vm(*, cluster_name: str, install_config_yaml: str) -> None:
    base_dir = os.environ.get("INSTALLER_VM_WORKDIR", "/home/devops")
    cluster_dir = f"{base_dir}/az-{cluster_name}-cluster"
    target_path = f"{cluster_dir}/install-config.yaml"
    backup_path = f"{base_dir}/install-config.backup.yaml"
    tmp_path = f"/tmp/install-config-{cluster_name}.yaml"

    _log("Opening SSH for install-config push...")
    client = _connect()
    try:
        sftp = client.open_sftp()
        try:
            with sftp.file(tmp_path, "w") as f:
                f.write(install_config_yaml)
        finally:
            sftp.close()

        _exec(client, f"sudo mkdir -p {cluster_dir}")
        _exec(client, f"if [ -f {target_path} ]; then sudo cp {target_path} {backup_path}; fi")
        _exec(client, f"sudo mv {tmp_path} {target_path}")
        _exec(client, f"sudo chown devops:devops {target_path}")
        _exec(client, f"sudo chmod 600 {target_path}")

        _log("install-config pushed ")

    finally:
        try:
            client.close()
        except Exception:
            pass