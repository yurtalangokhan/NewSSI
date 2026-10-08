"""Startup guard: every service-to-service URL must route through Gateway.

Services no longer authenticate callers themselves, so a URL that points
straight at a service host does not merely bypass route authorization — it
fails with 401 on every request. That is a configuration error worth catching at
boot with a clear message, not at runtime as a wall of unexplained 401s.

A Gateway URL is recognised by its route prefix: APISIX exposes services under
``/<service>`` for user traffic and ``/internal/<service>`` for machine traffic.
A bare origin such as ``http://user-service:8090`` has no such prefix and is
rejected.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from error_contract import GatewayRoutingError

GATEWAY_ROUTE_PREFIXES = (
    "/agent-service",
    "/user-service",
    "/rag-service",
    "/tools-service",
    "/internal/agent-service",
    "/internal/user-service",
    "/internal/rag-service",
    "/internal/tools-service",
)


def is_gateway_routed(url: str | None) -> bool:
    """True when the URL carries a Gateway route prefix."""
    if not url or not url.strip():
        return False
    path = urlsplit(url.strip()).path.rstrip("/")
    return any(path == prefix or path.startswith(prefix + "/") for prefix in GATEWAY_ROUTE_PREFIXES)


def assert_gateway_routed(urls: dict[str, str | None], *, required: bool = True) -> None:
    """Validate configured service URLs, raising on any that bypass Gateway.

    ``required=False`` tolerates unset values (an optional integration), but a
    value that is set must still route through Gateway.
    """
    offenders: list[str] = []
    for name, url in urls.items():
        value = (url or "").strip()
        if not value:
            if required:
                offenders.append(f"{name} is not set")
            continue
        if not is_gateway_routed(value):
            offenders.append(f"{name}={value!r} does not route through Gateway")

    if offenders:
        raise GatewayRoutingError(
            "Service URLs must go through Gateway "
            "(e.g. http://apisix:8000/internal/user-service). Offending settings: " + "; ".join(offenders)
        )


__all__ = [
    "GATEWAY_ROUTE_PREFIXES",
    "GatewayRoutingError",
    "assert_gateway_routed",
    "is_gateway_routed",
]
