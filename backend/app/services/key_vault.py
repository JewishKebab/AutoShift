# app/services/key_vault.py
import os
from typing import Optional

from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient

_cred: Optional[ClientSecretCredential] = None
_client: Optional[SecretClient] = None


def _get_credential() -> ClientSecretCredential:
    global _cred
    if _cred is not None:
        return _cred

    _cred = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
    return _cred


def _get_client() -> SecretClient:
    global _client
    if _client is not None:
        return _client

    vault_url = (os.environ.get("KEY_VAULT_URL") or "").strip()
    if not vault_url:
        raise RuntimeError("Missing KEY_VAULT_URL env var (e.g. https://<vault>.vault.azure.net/)")

    _client = SecretClient(vault_url=vault_url, credential=_get_credential())
    return _client


def _sanitize_secret_name(s: str) -> str:
    # Key Vault secret name: [0-9a-zA-Z-]+
    s = (s or "").strip().lower()
    out = []
    for ch in s:
        out.append(ch if (ch.isalnum() or ch == "-") else "-")
    name = "".join(out).strip("-")
    return name or "cluster"


def _secret_name_for_cluster(cluster_name: str) -> str:
    return f"{_sanitize_secret_name(cluster_name)}-kubeadmin-password"


def store_kubeadmin_password(*, cluster_name: str, password: str) -> str:
    """
    Secret name: <cluster>-kubeadmin-password
    Returns the secret id.
    """
    pw = (password or "").strip()
    if not pw:
        raise ValueError("Empty kubeadmin password")

    client = _get_client()
    secret_name = _secret_name_for_cluster(cluster_name)

    resp = client.set_secret(secret_name, pw)
    return resp.id


# def delete_kubeadmin_password_secret(*, cluster_name: str) -> bool:
#     """
#     Deletes the kubeadmin password secret for this cluster if it exists.
#     Returns True if a delete was started, False if it was not found.
#     """
#     client = _get_client()
#     secret_name = _secret_name_for_cluster(cluster_name)

#     try:
#         poller = client.begin_delete_secret(secret_name)
#         poller.result()  # wait for delete to complete
#         return True
#     except Exception as e:
#         # If you want exact handling: ResourceNotFoundError from azure.core.exceptions
#         msg = str(e).lower()
#         if "notfound" in msg or "not found" in msg:
#             return False
#         raise

def delete_kubeadmin_password(*, cluster_name: str) -> None:
    """
    Deletes the secret named: <cluster>-kubeadmin-password
    Note: KeyVault delete is often soft-delete (depending on vault settings).
    """
    client = _get_client()
    secret_name = f"{_sanitize_secret_name(cluster_name)}-kubeadmin-password"

    # begin_delete_secret returns a poller in newer SDK versions
    poller = client.begin_delete_secret(secret_name)
    poller.result()

    # Optional purge (only if your vault has soft-delete+purge protection rules that allow it)
    if (os.environ.get("KEY_VAULT_PURGE_ON_DELETE") or "").lower() in ("1", "true", "yes"):
        try:
            client.purge_deleted_secret(secret_name)
        except Exception:
            # purge can fail if not allowed; ignore
            pass
