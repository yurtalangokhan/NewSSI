"""Outbound URL policy. Spec TS-6.

The check that matters runs on resolved IP addresses, never on the
textual host: decimal, octal, hex and IPv4-mapped-IPv6 forms all defeat
textual parsing, and any check done only on the URL string can be
bypassed by a hostname that resolves to an internal address.
"""

import asyncio
import socket
import time

import pytest

from security import UrlPolicyError, validate_url
from security.url_policy import (
    is_blocked_ip,
    is_metadata_address,
    resolve_addresses,
    resolve_addresses_async,
    resolve_and_check,
    resolve_and_check_async,
)


@pytest.mark.parametrize(
    "url",
    ["https://example.com/a", "http://example.com:8080/b"],
)
def test_allowed_schemes(url):
    assert validate_url(url).hostname == "example.com"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://example.com/",
        "ftp://example.com/",
        "javascript:alert(1)",
        "data:text/html,<script>",
    ],
)
def test_rejected_schemes(url):
    with pytest.raises(UrlPolicyError):
        validate_url(url)


def test_url_without_host_is_rejected():
    with pytest.raises(UrlPolicyError):
        validate_url("https:///nohost")


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
    ],
)
def test_private_and_special_ips_are_blocked(ip):
    assert is_blocked_ip(ip) is True


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888"])
def test_public_ips_are_allowed(ip):
    assert is_blocked_ip(ip) is False


def test_garbage_input_is_treated_as_blocked():
    assert is_blocked_ip("not-an-ip") is True


def test_decimal_encoded_localhost_is_blocked_after_resolution(monkeypatch):
    # 2130706433 == 127.0.0.1. The check must happen on the resolved
    # address, never on the textual host, since encoding tricks like this
    # (also octal, hex, IPv4-mapped IPv6) defeat any check on the string.
    monkeypatch.setattr(
        "security.url_policy._getaddrinfo_hosts", lambda host, port: ["127.0.0.1"]
    )
    with pytest.raises(UrlPolicyError):
        resolve_and_check("2130706433", 80)


def test_hostname_resolving_to_internal_ip_is_blocked(monkeypatch):
    monkeypatch.setattr(
        "security.url_policy._getaddrinfo_hosts", lambda host, port: ["10.0.0.5"]
    )
    with pytest.raises(UrlPolicyError):
        resolve_and_check("internal.example.com", 443)


def test_hostname_resolving_to_public_ip_returns_the_address(monkeypatch):
    monkeypatch.setattr(
        "security.url_policy._getaddrinfo_hosts", lambda host, port: ["93.184.216.34"]
    )
    assert resolve_and_check("example.com", 443) == "93.184.216.34"


def test_a_host_resolving_to_any_internal_address_is_blocked(monkeypatch):
    """A host resolving to both a public and a private address must be
    rejected: otherwise the client could still connect to the private one
    on a later attempt or a different resolver order."""
    monkeypatch.setattr(
        "security.url_policy._getaddrinfo_hosts",
        lambda host, port: ["93.184.216.34", "10.0.0.5"],
    )
    with pytest.raises(UrlPolicyError):
        resolve_and_check("mixed.example.com", 443)


def test_unresolvable_host_raises_policy_error(monkeypatch):
    # Patch the underlying socket.getaddrinfo (not _getaddrinfo_hosts
    # itself) so this exercises _getaddrinfo_hosts's own gaierror ->
    # UrlPolicyError conversion rather than bypassing it.
    import socket

    def _raise(*args, **kwargs):
        raise socket.gaierror("nope")

    monkeypatch.setattr("security.url_policy.socket.getaddrinfo", _raise)
    with pytest.raises(UrlPolicyError):
        resolve_and_check("does-not-resolve.invalid", 443)


async def test_resolve_and_check_async_returns_the_resolved_address(monkeypatch):
    monkeypatch.setattr(
        "security.url_policy._getaddrinfo_hosts", lambda host, port: ["93.184.216.34"]
    )
    assert await resolve_and_check_async("example.com", 443) == "93.184.216.34"


async def test_resolve_and_check_async_blocks_internal_address(monkeypatch):
    monkeypatch.setattr(
        "security.url_policy._getaddrinfo_hosts", lambda host, port: ["10.0.0.5"]
    )
    with pytest.raises(UrlPolicyError):
        await resolve_and_check_async("internal.example.com", 443)


async def test_resolve_and_check_async_does_not_block_the_event_loop(monkeypatch):
    """A slow DNS lookup must run off the event loop thread: other coroutines
    scheduled on the same loop should keep making progress while it resolves."""

    def slow_getaddrinfo(host, port):
        time.sleep(0.2)
        return ["93.184.216.34"]

    monkeypatch.setattr("security.url_policy._getaddrinfo_hosts", slow_getaddrinfo)

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    ticker_task = asyncio.create_task(ticker())
    try:
        await resolve_and_check_async("example.com", 443)
    finally:
        ticker_task.cancel()

    assert ticks >= 5


async def test_resolve_and_check_async_times_out_without_waiting_for_the_full_lookup(
    monkeypatch,
):
    def slow_getaddrinfo(host, port):
        time.sleep(0.5)
        return ["93.184.216.34"]

    monkeypatch.setattr("security.url_policy._getaddrinfo_hosts", slow_getaddrinfo)

    start = time.monotonic()
    with pytest.raises(UrlPolicyError, match="timed out"):
        await resolve_and_check_async("example.com", 443, timeout=0.05)
    assert time.monotonic() - start < 0.3


# --- the seams a service needs to keep its own policy -------------------------
#
# resolve_addresses hands back every address and is_metadata_address answers a
# narrower question than is_blocked_ip, so a caller that relaxes the
# private-network rule for its own deployment can still refuse cloud metadata.


def test_resolve_addresses_returns_every_address(monkeypatch):
    monkeypatch.setattr(
        "security.url_policy._getaddrinfo_hosts",
        lambda host, port: ["93.184.216.34", "10.0.0.7"],
    )
    # Both come back, including the internal one: choosing which to refuse is
    # the caller's policy decision, not this function's.
    assert resolve_addresses("example.com", 443) == ["93.184.216.34", "10.0.0.7"]


def test_resolve_addresses_rejects_a_host_with_no_addresses(monkeypatch):
    monkeypatch.setattr("security.url_policy._getaddrinfo_hosts", lambda host, port: [])
    with pytest.raises(UrlPolicyError, match="No addresses"):
        resolve_addresses("example.com", 443)


def test_resolve_addresses_reports_an_unresolvable_host(monkeypatch):
    def boom(*args, **kwargs):
        raise socket.gaierror("nope")

    monkeypatch.setattr("security.url_policy.socket.getaddrinfo", boom)
    with pytest.raises(UrlPolicyError, match="Could not resolve"):
        resolve_addresses("example.com", 443)


async def test_resolve_addresses_async_does_not_block_the_event_loop(monkeypatch):
    def slow_getaddrinfo(host, port):
        time.sleep(0.3)
        return ["93.184.216.34"]

    monkeypatch.setattr("security.url_policy._getaddrinfo_hosts", slow_getaddrinfo)

    ticks = 0

    async def tick():
        nonlocal ticks
        for _ in range(5):
            await asyncio.sleep(0.01)
            ticks += 1

    result, _ = await asyncio.gather(
        resolve_addresses_async("example.com", 443), tick()
    )
    assert result == ["93.184.216.34"]
    assert ticks >= 5


async def test_resolve_addresses_async_times_out(monkeypatch):
    def slow_getaddrinfo(host, port):
        time.sleep(0.5)
        return ["93.184.216.34"]

    monkeypatch.setattr("security.url_policy._getaddrinfo_hosts", slow_getaddrinfo)

    with pytest.raises(UrlPolicyError, match="timed out"):
        await resolve_addresses_async("example.com", 443, timeout=0.05)


@pytest.mark.parametrize(
    "address",
    [
        "169.254.169.254",  # AWS/Azure/GCP instance metadata
        "169.254.0.1",  # the rest of link-local
        "::ffff:169.254.169.254",  # the same address in IPv4-mapped form
        "fe80::1",
        "fd00:ec2::254",  # AWS IPv6 metadata
    ],
)
def test_metadata_addresses_are_recognised(address):
    assert is_metadata_address(address) is True


@pytest.mark.parametrize("address", ["10.0.0.5", "192.168.1.1", "93.184.216.34", "::1"])
def test_ordinary_addresses_are_not_metadata(address):
    assert is_metadata_address(address) is False


def test_garbage_is_not_treated_as_metadata():
    """Fail-open here is safe: callers still apply is_blocked_ip, which fails closed."""
    assert is_metadata_address("not-an-ip") is False


def test_metadata_is_stricter_than_the_private_blocklist_only_where_it_matters():
    """An operator opting into private egress must still not reach metadata."""
    assert is_metadata_address("10.0.0.5") is False
    assert is_blocked_ip("10.0.0.5") is True
