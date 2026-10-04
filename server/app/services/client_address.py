# server/app/services/client_address.py
"""The caller's real network address, used as part of the sign-in throttle key.

Behind a proxy or tunnel the direct peer is the proxy for every caller, so the per-address
part of the throttle protected nothing. X-Forwarded-For is believed only when the direct
peer is a configured proxy (TRUSTED_PROXY_IPS); it is read from the right, skipping other
trusted proxies, so a caller cannot choose its own address by adding a fake first entry.
"""
import ipaddress
from typing import Optional

from server.app.config import settings


def resolve_client_address(peer: str, forwarded_for: str, trusted: set[str]) -> str:
    if peer not in trusted or not forwarded_for:
        return peer
    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    for hop in reversed(hops):
        try:
            ipaddress.ip_address(hop)
        except ValueError:
            return peer  # a malformed chain is not trusted at all
        if hop not in trusted:
            return hop
    return peer


def client_address(request, trusted: Optional[set[str]] = None) -> str:
    peer = request.client.host if request.client else "unknown"
    return resolve_client_address(
        peer,
        request.headers.get("x-forwarded-for", ""),
        settings.trusted_proxy_list if trusted is None else trusted,
    )