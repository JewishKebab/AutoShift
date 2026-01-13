import datetime as dt
import re
import requests
from azure.identity import ClientSecretCredential

API_VERSION = "2022-07-01-preview"

def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

def _tomorrow_utc_same_time() -> dt.datetime:
    return _utc_now() + dt.timedelta(days=1)

def _to_arm_time(t: dt.datetime) -> str:
    # ISO 8601 with Z (Azure accepts this)
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _safe_name(s: str) -> str:
    # Azure resource name safe-ish: letters, numbers, -, _
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9_-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "cluster"

def _get_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    cred = ClientSecretCredential(tenant_id=tenant_id, client_id=client_id, client_secret=client_secret)
    token = cred.get_token("https://management.azure.com/.default")
    return token.token

def list_exemptions_for_assignment(
    *,
    subscription_id: str,
    policy_assignment_id: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
) -> list[dict]:
    """
    Returns non-expired exemptions at subscription scope for a specific policyAssignmentId.
    """
    token = _get_token(tenant_id, client_id, client_secret)
    headers = {"Authorization": f"Bearer {token}"}

    # Use the REST list filter: policyAssignmentId eq '{value}' and excludeExpired()
    # filter support documented for List. :contentReference[oaicite:1]{index=1}
    filter_q = f"policyAssignmentId eq '{policy_assignment_id}' and excludeExpired()"
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/providers/Microsoft.Authorization/policyExemptions"
        f"?api-version={API_VERSION}&$filter={requests.utils.quote(filter_q, safe='')}"
    )

    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json() or {}
    return data.get("value", []) or []

def create_subscription_exemption(
    *,
    subscription_id: str,
    exemption_name: str,
    policy_assignment_id: str,
    expires_on_utc: dt.datetime,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    display_name: str,
    description: str,
    exemption_category: str = "Waiver",
) -> dict:
    """
    Creates/updates a policy exemption at subscription scope.
    Properties include expiresOn. :contentReference[oaicite:2]{index=2}
    """
    token = _get_token(tenant_id, client_id, client_secret)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    scope = f"/subscriptions/{subscription_id}"
    url = (
        f"https://management.azure.com{scope}"
        f"/providers/Microsoft.Authorization/policyExemptions/{exemption_name}"
        f"?api-version={API_VERSION}"
    )

    body = {
        "properties": {
            "policyAssignmentId": policy_assignment_id,
            "exemptionCategory": exemption_category,  # Waiver or Mitigated
            "displayName": display_name,
            "description": description,
            "expiresOn": _to_arm_time(expires_on_utc),
        }
    }

    r = requests.put(url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    return r.json()

def build_exemption_name(cluster_name: str) -> str:
    # Deterministic-ish and unique per day
    safe = _safe_name(cluster_name)
    stamp = _utc_now().strftime("%Y%m%d")
    return f"autoshift-{safe}-{stamp}"
