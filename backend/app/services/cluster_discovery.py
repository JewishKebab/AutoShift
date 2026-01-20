import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import paramiko
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.privatedns import PrivateDnsManagementClient

# Strict RG pattern:
# - RG must be all lowercase (enforced in code)
# - cluster name must contain "opensh" (so opensh/openshi/openshift all match)
# - ends with "-<5 lowercase alnum>-rg"
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

    # NEW: cert bundle presence on installer VM
    cert_zip_found: bool = False
    cert_zip_path: str = ""

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
            "certZipFound": self.cert_zip_found,
            "certZipPath": self.cert_zip_path,
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
# Cert bundle lookup on VM
# ---------------------------

_cert_cache: Dict[str, Tuple[float, bool]] = {}


def _cert_zip_path_for_cluster(cluster_name: str) -> str:
    base_dir = os.environ.get("INSTALLER_BASE_DIR", "/home/devops").rstrip("/")
    # IMPORTANT: do NOT inject "-openshift" here
    cluster_dir = f"az-{cluster_name}-cluster"
    return f"{base_dir}/{cluster_dir}/certs/certs.zip"


def _has_cert_zip_on_vm(cluster_name: str, ttl_seconds: int = 20) -> bool:
    now = time.time()
    cached = _cert_cache.get(cluster_name)
    if cached and (now - cached[0]) < ttl_seconds:
        return cached[1]

    host = os.environ.get("INSTALLER_VM_HOST", "").strip()
    password = os.environ.get("INSTALLER_VM_PASSWORD", "").strip()
    if not host or not password:
        _cert_cache[cluster_name] = (now, False)
        return False

    user = os.environ.get("INSTALLER_VM_USER", "asgard")
    zip_path = _cert_zip_path_for_cluster(cluster_name)

    # Use a simple test that returns YES/NO so we can parse reliably
    cmd = f"bash -lc 'test -f {zip_path!s} && echo YES || echo NO'"
    try:
        out = _ssh_exec(host, user, password, cmd, timeout=12)
        ok = "YES" in (out or "")
        _cert_cache[cluster_name] = (now, ok)
        return ok
    except Exception:
        _cert_cache[cluster_name] = (now, False)
        return False


# ---------------------------
# DNS zone lookup
# ---------------------------

def _list_private_dns_zone_names(zone_subscription: str) -> set:
    pdns = _privatedns_client(zone_subscription)
    names = set()
    for z in pdns.private_zones.list():
        if z.name:
            names.add(z.name.lower())
    return names


_dns_rg_cache: Dict[Tuple[str, str], Tuple[float, bool]] = {}


def _rg_has_any_private_dns_zone(subscription_id: str, rg_name: str, ttl_seconds: int = 60) -> bool:
    key = (subscription_id, rg_name)
    now = time.time()

    cached = _dns_rg_cache.get(key)
    if cached and (now - cached[0]) < ttl_seconds:
        return cached[1]

    pdns = _privatedns_client(subscription_id)
    try:
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
                    {"resourceGroup": rg_name, "clusterName": m.group("name"), "infra": m.group("infra")}
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

    cache_ttl = int(os.environ.get("DISCOVER_CLUSTERS_CACHE_TTL", "20"))
    dns_suffix = os.environ.get("DNS_ZONE_SUFFIX", "").strip()

    cache_key = (cluster_subscription, zone_subscription, base_domain, dns_suffix)
    now = time.time()
    cached = _discover_cache.get(cache_key)
    if cached:
        ts, data = cached
        if data and (now - ts) < cache_ttl:
            return data

    try:
        ps_out = _installer_processes_cached(ttl_seconds=10)
    except Exception:
        ps_out = ""

    try:
        dns_zone_names = _list_private_dns_zone_names(zone_subscription)
    except Exception:
        dns_zone_names = set()

    out: List[Dict] = []

    for rg in rclient.resource_groups.list():
        rg_name = rg.name or ""
        if not rg_name:
            continue

        if rg_name != rg_name.lower():
            continue

        m = RG_RE.match(rg_name)
        if not m:
            continue

        cluster_name = m.group("name")
        infra = m.group("infra")

        zone_name = f"{cluster_name}{dns_suffix}.{base_domain}"

        dns_found = _rg_has_any_private_dns_zone(zone_subscription, rg_name)
        if not dns_found and dns_zone_names:
            dns_found = zone_name.lower() in dns_zone_names

        # Only include running clusters
        if not dns_found:
            continue

        # NEW: check cert zip presence on VM
        cert_zip_path = _cert_zip_path_for_cluster(cluster_name)
        cert_zip_found = _has_cert_zip_on_vm(cluster_name, ttl_seconds=20)

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
                cert_zip_found=cert_zip_found,
                cert_zip_path=cert_zip_path,
            ).to_dict()
        )

    out.sort(key=lambda c: c["name"].lower())
    _discover_cache[cache_key] = (now, out)
    return out
