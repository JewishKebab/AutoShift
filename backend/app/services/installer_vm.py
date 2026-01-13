# app/services/installer_vm.py
import os
import socket
import time
from typing import Dict, Optional

from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient

_cred: Optional[ClientSecretCredential] = None
_compute_clients: Dict[str, ComputeManagementClient] = {}


def _log(msg: str) -> None:
    print(f"[installer-vm] {msg}", flush=True)


def _get_credential() -> ClientSecretCredential:
    global _cred
    if _cred is not None:
        return _cred

    _log("Creating Azure credential")
    _cred = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
    return _cred


def _compute_client(subscription_id: str) -> ComputeManagementClient:
    client = _compute_clients.get(subscription_id)
    if client:
        return client

    _log(f"Creating ComputeManagementClient for subscription {subscription_id}")
    client = ComputeManagementClient(_get_credential(), subscription_id)
    _compute_clients[subscription_id] = client
    return client


def _env() -> Dict[str, str]:
    return {
        "subscription_id": os.environ["SUBSCRIPTION_ID"],
        "resource_group": os.environ["AZ_RESOURCE_GROUP"],
        "vm_name": os.environ["INSTALLER_VM_NAME"],
    }


def get_power_state() -> str:
    env = _env()
    compute = _compute_client(env["subscription_id"])

    iv = compute.virtual_machines.instance_view(env["resource_group"], env["vm_name"])
    for status in iv.statuses or []:
        code = (status.code or "").strip()
        if code.lower().startswith("powerstate/"):
            state = code.split("/", 1)[1].lower()
            _log(f"Current power state: {state}")
            return state

    _log("Power state unknown")
    return "unknown"


def start_vm() -> None:
    env = _env()
    compute = _compute_client(env["subscription_id"])

    _log(f"Starting VM '{env['vm_name']}' in RG '{env['resource_group']}'")
    poller = compute.virtual_machines.begin_start(env["resource_group"], env["vm_name"])
    poller.result()
    _log("Azure begin_start completed")


def wait_until_running(timeout_seconds: int = 900, poll_interval_seconds: int = 5) -> None:
    _log(f"Waiting for VM to reach 'running' (timeout={timeout_seconds}s)")
    start = time.time()
    while time.time() - start < timeout_seconds:
        if get_power_state() == "running":
            _log("VM is running")
            return
        time.sleep(poll_interval_seconds)

    raise TimeoutError(
        f"Installer VM '{os.environ['INSTALLER_VM_NAME']}' did not reach running state "
        f"within {timeout_seconds} seconds"
    )


def wait_for_tcp(
    host: str,
    port: int = 22,
    timeout_seconds: int = 900,
    poll_interval_seconds: int = 3,
) -> None:
    _log(f"Waiting for TCP {host}:{port} (timeout={timeout_seconds}s)")
    start = time.time()
    last_err: Optional[Exception] = None
    last_print = 0.0

    while time.time() - start < timeout_seconds:
        try:
            with socket.create_connection((host, port), timeout=5):
                _log("TCP port reachable ✅")
                return
        except OSError as e:
            last_err = e

        # print a heartbeat every ~30s so you see progress
        now = time.time()
        if now - last_print > 30:
            last_print = now
            _log(f"Still waiting for TCP... (last error: {type(last_err).__name__}: {last_err})")

        time.sleep(poll_interval_seconds)

    raise TimeoutError(
        f"Installer VM SSH port not reachable at {host}:{port} within {timeout_seconds}s "
        f"(last error: {last_err})"
    )


def ensure_installer_vm_ready(
    *,
    host: str,
    power_timeout_seconds: int = 900,
    ssh_timeout_seconds: int = 900,
) -> Dict[str, str]:
    """
    Ensures installer VM is:
      1) PowerState/running
      2) TCP port 22 reachable
    """
    _log("Ensuring installer VM is ready (power + TCP)")
    before = get_power_state()
    action = "none"

    if before != "running":
        _log(f"VM is not running (state={before}), starting it")
        start_vm()
        wait_until_running(timeout_seconds=power_timeout_seconds)
        action = f"started-from-{before}"
    else:
        _log("VM already running")

    wait_for_tcp(host, 22, timeout_seconds=ssh_timeout_seconds)
    _log("Installer VM ready ✅")

    return {
        "vm": os.environ["INSTALLER_VM_NAME"],
        "state": "running",
        "action": action,
    }
