import os
import time
from typing import Callable, Optional

from azure.identity import ClientSecretCredential
from azure.core.exceptions import HttpResponseError
from azure.mgmt.privatedns import PrivateDnsManagementClient
from azure.mgmt.network import NetworkManagementClient


# Hub subscription (VNets live here)
HUB_SUBSCRIPTION_ID = "80d0a5f6-1471-4cca-9a40-5ea81b9f7c19"

# Private DNS zones are created here (per your environment)
ZONE_SUBSCRIPTION_ID = "94893b9b-e69d-4648-823c-a72a0b9ede71"

TARGET_VNET_NAMES = [
    "Hub-Bsmch-Prod-In-Vnet",
    "Hub-Bsmch-Prod-Proxy-Vnet",
]


def _credential() -> ClientSecretCredential:
    return ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )


def _extract_rg_from_resource_id(resource_id: str) -> Optional[str]:
    # /subscriptions/<sub>/resourceGroups/<rg>/providers/...
    parts = (resource_id or "").split("/")
    try:
        i = parts.index("resourceGroups")
        return parts[i + 1]
    except ValueError:
        return None
    except IndexError:
        return None


def _find_zone_rg_by_listing(pdns: PrivateDnsManagementClient, zone_name: str) -> Optional[str]:
    # list() enumerates zones across the subscription
    for z in pdns.private_zones.list():
        if (z.name or "").lower() == zone_name.lower():
            rg = _extract_rg_from_resource_id(z.id or "")
            if rg:
                return rg
    return None


def _find_vnet_id_by_name(net: NetworkManagementClient, vnet_name: str) -> str:
    for vnet in net.virtual_networks.list_all():
        if vnet.name == vnet_name and vnet.id:
            return vnet.id
    raise RuntimeError(f"[dns] VNet not found in hub subscription: {vnet_name}")


def link_private_dns_zone_to_hubs(
    *,
    cluster_name: str,
    log: Optional[Callable[[str], None]] = None,
    poll_seconds: int = 20,
    timeout_seconds: int = 1800,
) -> None:
    def _log(msg: str):
        if log:
            log(msg)

    base_domain = os.environ["OCP_BASE_DOMAIN"]  # bsmch.net
    zone_name = f"{cluster_name}-openshift.{base_domain}"

    _log("[dns] ===========================================")
    _log("[dns] private DNS watcher starting (RG auto-detect)")
    _log(f"[dns] cluster_name={cluster_name}")
    _log(f"[dns] base_domain={base_domain}")
    _log(f"[dns] zone_name={zone_name}")
    _log(f"[dns] zone_subscription={ZONE_SUBSCRIPTION_ID}")
    _log(f"[dns] hub_subscription={HUB_SUBSCRIPTION_ID}")
    _log(f"[dns] target_vnets={TARGET_VNET_NAMES}")
    _log("[dns] ===========================================")

    cred = _credential()
    pdns = PrivateDnsManagementClient(cred, ZONE_SUBSCRIPTION_ID)
    net = NetworkManagementClient(cred, HUB_SUBSCRIPTION_ID)

    # ---- wait until zone exists, and discover its RG dynamically ----
    start = time.time()
    zone_rg: Optional[str] = None

    while True:
        try:
            zone_rg = _find_zone_rg_by_listing(pdns, zone_name)
            if zone_rg:
                _log(f"[dns] zone detected: {zone_name} (rg={zone_rg})")
                break

            if time.time() - start > timeout_seconds:
                raise RuntimeError(f"[dns] timed out waiting for zone: {zone_name}")

            _log("[dns] zone not found yet, waiting...")
            time.sleep(poll_seconds)

        except HttpResponseError as e:
            raise RuntimeError(f"[dns] failed while listing zones: {e}") from e

    # ---- resolve hub vnets ----
    _log("[dns] resolving hub vnet ids...")
    vnet_ids = {}
    for vnet_name in TARGET_VNET_NAMES:
        vnet_id = _find_vnet_id_by_name(net, vnet_name)
        vnet_ids[vnet_name] = vnet_id
        _log(f"[dns] resolved {vnet_name} -> {vnet_id}")

    # ---- create links ----
    _log("[dns] creating virtual network links...")
    for vnet_name, vnet_id in vnet_ids.items():
        link_name = f"{cluster_name}-{vnet_name}-link"
        params = {
            "location": "global",
            "properties": {
                "virtualNetwork": {"id": vnet_id},
                "registrationEnabled": False,
            },
        }

        try:
            pdns.virtual_network_links.begin_create_or_update(
                resource_group_name=zone_rg,
                private_zone_name=zone_name,
                virtual_network_link_name=link_name,
                parameters=params,
            ).result()
            _log(f"[dns] linked {zone_name} -> {vnet_name} (link={link_name})")

        except HttpResponseError as e:
            raise RuntimeError(f"[dns] failed creating link {link_name}: {e}") from e

    _log("[dns] done: hub links created")
