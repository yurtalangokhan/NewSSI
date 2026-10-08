"""SSRF-resistant HTTP client.

Redirects are followed manually so that every hop is re-validated against
the same policy as the initial URL, instead of httpx's default
follow_redirects=True walking straight into a redirect target that was
never checked (this is exactly how web_tools.fetch_webpage and the
several other unguarded httpx.Client(follow_redirects=True) call sites
this package replaces were exploitable).

Known limitation: this client re-resolves and checks the host on every
call, but does not pin the TCP connection to the specific address that
passed the check -- httpx has no public hook for supplying a
pre-resolved address to its connection pool short of replacing the whole
transport. A DNS-rebinding attacker who can flip a hostname's resolution
between the check and httpx's own (separate) connection attempt a few
milliseconds later is not fully closed by this module alone. The
deployment is expected to pair this with network-level egress controls
(default-deny egress, an egress proxy) as the layer that actually closes
that gap -- see spec TS-6 / Task 30. Treat this client as raising the bar
for the common case (a hostname or IP literal pointing directly at an
internal target), not as a complete answer to DNS rebinding on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import ParseResult

import httpx

from .url_policy import UrlPolicyError, resolve_and_check_async, validate_url

DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_MAX_REDIRECTS = 3
DEFAULT_TIMEOUT = 15.0

#: Stripped from the request whenever a redirect crosses to a different host,
#: or downgrades from https to http on the same host -- credentials meant for
#: the original origin must not follow the Location header to wherever it
#: points, the way a browser or curl's default redirect handling would not
#: forward them either.
_SENSITIVE_REDIRECT_HEADERS = {"authorization", "cookie", "proxy-authorization"}


def _headers_for_hop(
    headers: dict[str, str] | None,
    *,
    original_host: str,
    original_scheme: str,
    hop_url: ParseResult,
) -> dict[str, str] | None:
    if not headers:
        return headers
    crosses_origin = hop_url.hostname != original_host
    downgrades_scheme = original_scheme == "https" and hop_url.scheme == "http"
    if not (crosses_origin or downgrades_scheme):
        return headers
    return {k: v for k, v in headers.items() if k.lower() not in _SENSITIVE_REDIRECT_HEADERS}


@dataclass(frozen=True)
class GuardedResponse:
    status_code: int
    text: str
    final_url: str
    truncated: bool


class SecureHTTPClient:
    """One long-lived client per service. Never follows redirects itself."""

    def __init__(
        self,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects
        self._client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(
                connect=timeout / 3, read=timeout, write=timeout, pool=timeout
            ),
            transport=transport,
        )

    async def aclose(self) -> None:
        if not self._client.is_closed:
            await self._client.aclose()

    async def fetch(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> GuardedResponse:
        current = url
        original = validate_url(url)
        for _ in range(self._max_redirects + 1):
            parsed = validate_url(current)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            # Resolved and checked on every hop; see the module docstring
            # for what this check does and does not guarantee.
            await resolve_and_check_async(parsed.hostname, port)

            hop_headers = _headers_for_hop(
                headers,
                original_host=original.hostname,
                original_scheme=original.scheme,
                hop_url=parsed,
            )
            response = await self._client.get(current, headers=hop_headers)

            if response.status_code in (301, 302, 303, 307, 308):
                await response.aclose()
                location = response.headers.get("location")
                if not location:
                    raise UrlPolicyError("Redirect without a Location header")
                current = str(httpx.URL(current).join(location))
                continue

            body = b""
            truncated = False
            async for chunk in response.aiter_bytes():
                remaining = self._max_bytes - len(body)
                if remaining <= 0:
                    truncated = True
                    break
                if len(chunk) > remaining:
                    body += chunk[:remaining]
                    truncated = True
                    break
                body += chunk
            await response.aclose()

            return GuardedResponse(
                status_code=response.status_code,
                text=body.decode("utf-8", errors="replace"),
                final_url=current,
                truncated=truncated,
            )

        raise UrlPolicyError(f"Exceeded {self._max_redirects} redirect hops")

# --- connection pooling -----------------------------------------------------
#
#
# import httpx
#

_ASYNC_CLIENTS: dict[str, httpx.AsyncClient] = {}
_SYNC_CLIENTS: dict[str, httpx.Client] = {}

DEFAULT_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)


def get_shared_client(name: str, **client_kwargs: object) -> httpx.AsyncClient:
    """Return the shared async client for `name`, creating it on first use.

    client_kwargs are only consulted the first time a given name is
    requested (or after close_all()); a later call with different kwargs
    for an already-created client does not reconfigure it, since httpx
    clients are not mutable after construction.
    """
    client = _ASYNC_CLIENTS.get(name)
    if client is None or client.is_closed:
        kwargs: dict[str, object] = {
            "limits": DEFAULT_LIMITS,
            "timeout": DEFAULT_TIMEOUT,
            **client_kwargs,
        }
        client = httpx.AsyncClient(**kwargs)
        _ASYNC_CLIENTS[name] = client
    return client


def get_shared_sync_client(name: str, **client_kwargs: object) -> httpx.Client:
    """Return the shared sync client for `name`, creating it on first use.

    Same contract as :func:`get_shared_client`, including "kwargs count only on
    first construction". Use this instead of module-level ``httpx.get`` /
    ``httpx.post``, each of which builds and discards a client — and therefore a
    connection pool — per call.
    """
    client = _SYNC_CLIENTS.get(name)
    if client is None or client.is_closed:
        kwargs: dict[str, object] = {
            "limits": DEFAULT_LIMITS,
            "timeout": DEFAULT_TIMEOUT,
            **client_kwargs,
        }
        client = httpx.Client(**kwargs)
        _SYNC_CLIENTS[name] = client
    return client


def close_all_sync() -> None:
    """Close every pooled sync client. Safe to call once per process."""
    for client in list(_SYNC_CLIENTS.values()):
        if not client.is_closed:
            client.close()
    _SYNC_CLIENTS.clear()


async def close_all() -> None:
    """Close every pooled client, async and sync. Call from the shutdown hook."""
    for client in list(_ASYNC_CLIENTS.values()):
        if not client.is_closed:
            await client.aclose()
    _ASYNC_CLIENTS.clear()
    close_all_sync()
