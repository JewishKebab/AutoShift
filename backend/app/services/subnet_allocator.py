from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from typing import Iterable


@dataclass(frozen=True)
class SubnetPairSuggestion:
    master_cidr: str
    worker_cidr: str


def _parse_networks(prefixes: Iterable[str]) -> list[ipaddress.IPv4Network]:
    nets: list[ipaddress.IPv4Network] = []
    for p in prefixes:
        try:
            # strict=False lets us accept things like "10.104.32.1/22" if Azure ever returns it oddly
            n = ipaddress.ip_network(p, strict=False)
            if isinstance(n, ipaddress.IPv4Network):
                nets.append(n)
        except Exception:
            # ignore garbage
            continue
    return nets


def _overlaps_any(candidate: ipaddress.IPv4Network, existing: list[ipaddress.IPv4Network]) -> bool:
    # True if candidate overlaps *any* existing subnet, regardless of prefix length (/26, /24, /22, etc)
    return any(candidate.overlaps(e) for e in existing)


def suggest_next_pair(
    existing_prefixes: list[str],
    *,
    base_prefix: str = "10.104",
    prefixlen: int = 22,
) -> SubnetPairSuggestion:
    """
    Find the next available /22 + /22 pair in the VNet address space.

    Critical behavior:
    - Treats ANY existing subnet as occupied, even smaller ones (e.g., /26 Bastion subnet).
    - Uses real overlap checks, not "exact match" checks.

    For base_prefix="10.104" and prefixlen=22:
    /22 blocks increment by 4 in the 3rd octet:
      0,4,8,12,...,32,36,40,44,...
    We return consecutive blocks as master+worker: N and N+4.
    """
    existing = _parse_networks(existing_prefixes)

    # We scan third octet in steps of 4 (0..252) for /22 pairs
    # master: 10.104.X.0/22
    # worker: 10.104.(X+4).0/22
    for third in range(0, 256, 4):
        third_worker = third + 4
        if third_worker > 252:
            break

        master_cidr = f"{base_prefix}.{third}.0/{prefixlen}"
        worker_cidr = f"{base_prefix}.{third_worker}.0/{prefixlen}"

        master_net = ipaddress.ip_network(master_cidr, strict=False)
        worker_net = ipaddress.ip_network(worker_cidr, strict=False)

        # sanity: ensure they're IPv4
        if not isinstance(master_net, ipaddress.IPv4Network) or not isinstance(worker_net, ipaddress.IPv4Network):
            continue

        # must not overlap ANY existing subnet (including tiny /26)
        if _overlaps_any(master_net, existing):
            continue
        if _overlaps_any(worker_net, existing):
            continue

        # also ensure the master/worker don't overlap each other (they won't, but keep it explicit)
        if master_net.overlaps(worker_net):
            continue

        return SubnetPairSuggestion(master_cidr=str(master_net), worker_cidr=str(worker_net))

    raise ValueError("No available /22+/22 pair found for the given base_prefix")
