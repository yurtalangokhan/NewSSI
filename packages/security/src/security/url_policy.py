"""Outbound URL policy.

The check that matters runs on resolved IP addresses, never on the
textual host: decimal, octal, hex and IPv4-mapped-IPv6 forms all defeat
textual parsing. This module is defence in depth -- the deployment is
expected to also run a default-deny egress policy (see spec TS-6 / Task
30), since a check inside the application process can never fully close
DNS-rebinding-style TOCTOU gaps on its own.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import ParseResult, urlparse

ALLOWED_SCHEMES = {"http", "https"}

#: socket.getaddrinfo is a blocking syscall; resolve_and_check_async runs it in
#: a worker thread and gives up after this long rather than stalling the event
#: loop for as long as a slow or unresponsive resolver takes.
DEFAULT_DNS_TIMEOUT_SECONDS = 5.0

BLOCKED_NETWORKS = [
    ipaddress.ip_network(cidr)
    for cidr in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
]

#: Instance-metadata endpoints (169.254.169.254 on AWS, GCP and Azure;
#: fd00:ec2::254 on AWS IPv6) plus the rest of link-local. Kept apart from
#: BLOCKED_NETWORKS so a service that opts into private-network egress still
#: cannot re-enable them.
METADATA_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fd00:ec2::/32"),
)


class UrlPolicyError(ValueError):
    """Raised when a URL or its resolved address violates the outbound policy."""


def validate_url(url: str) -> ParseResult:
    """Raise UrlPolicyError unless url has an allowed scheme and a host."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UrlPolicyError(f"Scheme {parsed.scheme!r} is not allowed")
    if not parsed.hostname:
        raise UrlPolicyError("URL must include a host")
    return parsed


def is_blocked_ip(address: str) -> bool:
    """True if address is private, loopback, link-local, reserved, or
    otherwise not a routable public address. Also true for garbage input
    that does not parse as an IP at all: fail closed."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    # An IPv4-mapped IPv6 address must be judged on its IPv4 form, or
    # ::ffff:127.0.0.1 would pass as a "public" IPv6 address.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
        return True
    return any(ip in network for network in BLOCKED_NETWORKS)


def _getaddrinfo_hosts(host: str, port: int | None) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UrlPolicyError(f"Could not resolve {host!r}") from exc
    return [info[4][0] for info in infos]


def resolve_addresses(host: str, port: int | None = None) -> list[str]:
    """Every address ``host`` resolves to, A and AAAA alike.

    Returns the whole list rather than one chosen address, so a caller that
    relaxes the private-network rule for its own deployment can still apply its
    own policy to each address. Picking one here would decide policy for it.
    """
    addresses = _getaddrinfo_hosts(host, port)
    if not addresses:
        raise UrlPolicyError(f"No addresses for {host!r}")
    return addresses


def is_metadata_address(address: str) -> bool:
    """True for cloud instance-metadata and link-local addresses.

    Separate from :func:`is_blocked_ip` because these stay refused even where a
    service lets an operator opt into private-network egress: reaching one
    yields instance credentials, which no deployment setting should re-enable.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip.version == net.version and ip in net for net in METADATA_NETWORKS)


def resolve_and_check(host: str, port: int) -> str:
    """Resolve host and return one address to connect to.

    Rejects the host if *any* resolved address is internal: a mixed
    result (some public, some private) would otherwise let a later
    connection attempt or a different resolver land on the private one.
    """
    addresses = resolve_addresses(host, port)
    for address in addresses:
        if is_blocked_ip(address):
            raise UrlPolicyError(f"{host!r} resolves to a blocked address ({address})")
    return addresses[0]


async def resolve_and_check_async(
    host: str, port: int, *, timeout: float = DEFAULT_DNS_TIMEOUT_SECONDS
) -> str:
    """Async wrapper around :func:`resolve_and_check`.

    getaddrinfo is a blocking syscall; running it directly on the event loop
    thread stalls every other coroutine in the process for as long as the
    resolver takes to answer. This runs it in a worker thread and bounds the
    wait, so a slow or unresponsive resolver degrades one caller instead of
    freezing the whole event loop.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(resolve_and_check, host, port), timeout=timeout
        )
    except TimeoutError as exc:
        raise UrlPolicyError(f"Resolution of {host!r} timed out after {timeout}s") from exc


async def resolve_addresses_async(
    host: str, port: int | None = None, *, timeout: float = DEFAULT_DNS_TIMEOUT_SECONDS
) -> list[str]:
    """Async :func:`resolve_addresses`, off the event loop and time-bounded.

    Same rationale as :func:`resolve_and_check_async`; this variant hands back
    every address so the caller can apply a policy that is not the default one.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(resolve_addresses, host, port), timeout=timeout
        )
    except TimeoutError as exc:
        raise UrlPolicyError(f"Resolution of {host!r} timed out after {timeout}s") from exc
