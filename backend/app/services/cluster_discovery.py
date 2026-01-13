import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import paramiko
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.privatedns import PrivateDnsManagementClient

#  Strict RG pattern:
# - RG must be all lowercase (enforced in code)
# - cluster name must contain "opensh" (so opensh/openshi/openshift all match)
# - ends with "-<5 lowercase alnum>-rg"
#
# Examples:
#   testing19-openshi-kw28x-rg
#   testing20-openshift-kw28x-rg
#   bsmch-prod-openshift-9ftcn-rg
RG_RE = re.compile(r"^(?P<name>[a-z0-9-]*opensh[a-z0-9-]*)-(?P<infra>[a-z0-9]{5})-rg$")


@dataclass
class DiscoveredCluster:
    id: str
    name: str
    infra: str
    resource_group: str
    subscription_id: str
    status: str
    dns_zone: str
    dns_zone_found: bool

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "infra": self.infra,
            "resourceGroup": self.resource_group,
            "subscriptionId": self.subscription_id,
            "status": self.status,
            "dnsZone": self.dns_zone,
            "dnsZoneFound": self.dns_zone_found,
        }


# ---------------------------
# Credential + client caching
# ---------------------------

_cred: Optional[ClientSecretCredential] = None
_resource_clients: Dict[str, ResourceManagementClient] = {}
_privatedns_clients: Dict[str, PrivateDnsManagementClient] = {}

# Cache for discover_clusters results
_discover_cache: Dict[Tuple[str, str, str, str], Tuple[float, List[Dict]]] = {}


def _get_credential() -> ClientSecretCredential:
    global _cred
    if _cred is not None:
        return _cred

    tenant = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_CLIENT_ID"]
    secret = os.environ["AZURE_CLIENT_SECRET"]
    _cred = ClientSecretCredential(tenant_id=tenant, client_id=client_id, client_secret=secret)
    return _cred


def _resource_client(subscription_id: str) -> ResourceManagementClient:
    c = _resource_clients.get(subscription_id)
    if c:
        return c
    c = ResourceManagementClient(_get_credential(), subscription_id)
    _resource_clients[subscription_id] = c
    return c


def _privatedns_client(subscription_id: str) -> PrivateDnsManagementClient:
    c = _privatedns_clients.get(subscription_id)
    if c:
        return c
    c = PrivateDnsManagementClient(_get_credential(), subscription_id)
    _privatedns_clients[subscription_id] = c
    return c


# ---------------------------
# SSH helper (installer VM)
# ---------------------------

def _ssh_exec(host: str, user: str, password: str, cmd: str, timeout: int = 12) -> str:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            hostname=host,
            username=user,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=timeout,
        )
        _, stdout, stderr = ssh.exec_command(cmd, get_pty=True, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="ignore")
        err = stderr.read().decode("utf-8", errors="ignore")
        return (out + "\n" + err).strip()
    finally:
        try:
            ssh.close()
        except Exception:
            pass


_ps_cache: Tuple[float, str] = (0.0, "")


def _installer_processes_cached(ttl_seconds: int = 10) -> str:
    global _ps_cache
    ts, data = _ps_cache
    now = time.time()
    if data and (now - ts) < ttl_seconds:
        return data

    # allow running without SSH creds (dev)
    host = os.environ.get("INSTALLER_VM_HOST", "").strip()
    password = os.environ.get("INSTALLER_VM_PASSWORD", "").strip()
    if not host or not password:
        _ps_cache = (now, "")
        return ""

    user = os.environ.get("INSTALLER_VM_USER", "asgard")
    cmd = r'ps aux | grep -E "openshift-install create cluster" | grep -v grep'
    out = _ssh_exec(host, user, password, cmd, timeout=12)

    _ps_cache = (now, out)
    return out


def _is_install_running_for_cluster(ps_output: str, cluster_name: str) -> bool:
    # folder naming: az-<cluster>-cluster
    return f"az-{cluster_name}-cluster" in (ps_output or "")


# ---------------------------
# DNS zone lookup
# ---------------------------

def _list_private_dns_zone_names(zone_subscription: str) -> set:
    """Fast subscription-wide list (paging) -> lowercase names."""
    pdns = _privatedns_client(zone_subscription)
    names = set()
    for z in pdns.private_zones.list():
        if z.name:
            names.add(z.name.lower())
    return names


# per-RG "any zone exists" check (cached)
_dns_rg_cache: Dict[Tuple[str, str], Tuple[float, bool]] = {}


def _rg_has_any_private_dns_zone(subscription_id: str, rg_name: str, ttl_seconds: int = 60) -> bool:
    key = (subscription_id, rg_name)
    now = time.time()

    cached = _dns_rg_cache.get(key)
    if cached and (now - cached[0]) < ttl_seconds:
        return cached[1]

    pdns = _privatedns_client(subscription_id)
    try:
        # if at least 1 zone exists in RG -> ok
        for _ in pdns.private_zones.list_by_resource_group(rg_name):
            _dns_rg_cache[key] = (now, True)
            return True
        _dns_rg_cache[key] = (now, False)
        return False
    except Exception:
        _dns_rg_cache[key] = (now, False)
        return False


# ---------------------------
# Main discovery
# ---------------------------

def discover_clusters(
    cluster_subscription: str,
    zone_subscription: str,
    base_domain: str = "bsmch.net",
    debug: Optional[str] = None,
) -> Union[List[Dict], Dict]:
    """
    debug:
      - None: normal mode -> List[Dict]
      - "rg": only list RGs + matches (no DNS, no SSH)
      - "dns": only list DNS zones timing (subscription-wide)
      - "ssh": only SSH ps timing
    """

    rclient = _resource_client(cluster_subscription)

    # -----------------------
    # Debug: RG only (fast)
    # -----------------------
    if debug == "rg":
        t0 = time.time()
        all_rgs: List[str] = []
        matched: List[Dict] = []

        for rg in rclient.resource_groups.list():
            rg_name = rg.name or ""
            if not rg_name:
                continue
            all_rgs.append(rg_name)

            if rg_name != rg_name.lower():
                continue

            m = RG_RE.match(rg_name)
            if m:
                matched.append(
                    {
                        "resourceGroup": rg_name,
                        "clusterName": m.group("name"),
                        "infra": m.group("infra"),
                    }
                )

        return {
            "debugMode": "rg",
            "subscriptionId": cluster_subscription,
            "totalResourceGroups": len(all_rgs),
            "matchedClusters": len(matched),
            "allResourceGroups": all_rgs[:500],
            "matches": matched,
            "elapsedSeconds": round(time.time() - t0, 3),
        }

    # -----------------------
    # Debug: DNS only
    # -----------------------
    if debug == "dns":
        t0 = time.time()
        names = _list_private_dns_zone_names(zone_subscription)
        return {
            "debugMode": "dns",
            "zoneSubscription": zone_subscription,
            "count": len(names),
            "sample": sorted(list(names))[:50],
            "elapsedSeconds": round(time.time() - t0, 3),
        }

    # -----------------------
    # Debug: SSH only
    # -----------------------
    if debug == "ssh":
        t0 = time.time()
        try:
            ps = _installer_processes_cached(ttl_seconds=0)
            ok = True
            err = None
        except Exception as e:
            ps = ""
            ok = False
            err = str(e)

        return {
            "debugMode": "ssh",
            "ok": ok,
            "error": err,
            "output": ps[:4000],
            "elapsedSeconds": round(time.time() - t0, 3),
        }

    # -----------------------
    # Normal mode: ONLY RUNNING
    # -----------------------

    cache_ttl = int(os.environ.get("DISCOVER_CLUSTERS_CACHE_TTL", "20"))
    dns_suffix = os.environ.get("DNS_ZONE_SUFFIX", "").strip()

    cache_key = (cluster_subscription, zone_subscription, base_domain, dns_suffix)
    now = time.time()
    cached = _discover_cache.get(cache_key)
    if cached:
        ts, data = cached
        if data and (now - ts) < cache_ttl:
            return data

    # SSH optional (we no longer use it for status, but keep it for future debug)
    try:
        ps_out = _installer_processes_cached(ttl_seconds=10)
    except Exception:
        ps_out = ""

    # subscription DNS names once (fallback)
    try:
        dns_zone_names = _list_private_dns_zone_names(zone_subscription)
    except Exception:
        dns_zone_names = set()

    out: List[Dict] = []

    for rg in rclient.resource_groups.list():
        rg_name = rg.name or ""
        if not rg_name:
            continue

        # enforce lowercase RGs only
        if rg_name != rg_name.lower():
            continue

        m = RG_RE.match(rg_name)
        if not m:
            continue

        cluster_name = m.group("name")
        infra = m.group("infra")

        zone_name = f"{cluster_name}{dns_suffix}.{base_domain}"

        # your rule: any zone in same RG == OK
        dns_found = _rg_has_any_private_dns_zone(zone_subscription, rg_name)

        # fallback: exact zone name exists in subscription
        if not dns_found and dns_zone_names:
            dns_found = zone_name.lower() in dns_zone_names

        # ✅ ONLY INCLUDE RUNNING CLUSTERS
        if not dns_found:
            continue

        out.append(
            DiscoveredCluster(
                id=f"{cluster_name}-{infra}",
                name=cluster_name,
                infra=infra,
                resource_group=rg_name,
                subscription_id=cluster_subscription,
                status="running",
                dns_zone=zone_name,
                dns_zone_found=True,
            ).to_dict()
        )

    out.sort(key=lambda c: c["name"].lower())
    _discover_cache[cache_key] = (now, out)
    return out
