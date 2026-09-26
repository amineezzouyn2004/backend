"""Client IP selection for minFraud. Do not trust X-Forwarded-For by default."""

from __future__ import annotations

import ipaddress
from typing import Protocol


class _ClientPeer(Protocol):
    host: str | None


class _HeadersLike(Protocol):
    def get(self, key: str) -> str | None: ...


class _RequestLike(Protocol):
    client: _ClientPeer | None
    headers: _HeadersLike


def is_public_ip(value: str) -> bool:
    try:
        parsed = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    return bool(parsed.is_global)


def client_ip_for_minfraud(
    request: _RequestLike,
    trusted_proxy_ips: list[str],
) -> str | None:
    """Return a public client IP only when the immediate peer is trusted.

    If ``trusted_proxy_ips`` is empty, forwarded headers are ignored. The
    connecting peer is used only when it is itself a public address.
    """
    trusted = {item.strip() for item in trusted_proxy_ips if item.strip()}
    peer = request.client.host if request.client else None
    if peer and peer in trusted:
        forwarded = request.headers.get("x-forwarded-for") or request.headers.get(
            "X-Forwarded-For"
        )
        if forwarded:
            parts = [part.strip() for part in forwarded.split(",") if part.strip()]
            for candidate in reversed(parts):
                if candidate in trusted:
                    continue
                if is_public_ip(candidate):
                    return candidate
            return None
        real_ip = request.headers.get("x-real-ip") or request.headers.get("X-Real-IP")
        if real_ip and is_public_ip(real_ip):
            return real_ip.strip()
        return None
    if peer and is_public_ip(peer):
        return peer
    return None
