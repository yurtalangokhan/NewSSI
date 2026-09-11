"""The transport contract for agent-service -> rag-service calls.

Every RAG call needs the same three decisions: which base URL, which bearer
token, how long to wait. Those decisions were previously re-made at each call
site, and the copies had drifted into three different fallbacks. Keeping them
here means a deployment change is one edit, and a new call site cannot invent
a fourth opinion.

`RAG_API_URL` is the setting; `RAG_SERVICE_API_URL` is the older name and is
still honoured. Both are absent from the checked-in `.env`, so the default
below is what dev actually runs against — see `docs/env-variables.md`.
"""

from __future__ import annotations

from core.env import env

# Kong's host-side address. In Docker, compose sets `RAG_API_URL` explicitly
# (`http://kong:8000/internal/rag-service`); on a developer's machine the
# services run on the host and reach Kong here.
DEFAULT_RAG_BASE_URL = "http://localhost:8000"

# Shared REST prefix every rag-service route sits under.
RAG_API_PREFIX = "/api/v1"

_DEFAULT_TIMEOUT_SECONDS = 15.0


def rag_base_url() -> str:
    """rag-service's root, without a trailing slash."""
    configured = env.RAG_API_URL or env.RAG_SERVICE_API_URL or DEFAULT_RAG_BASE_URL
    return configured.rstrip("/")


def rag_url(path: str) -> str:
    """Absolute rag-service URL for `path` under the shared REST prefix.

    `path` is the part after `/api/v1`, leading slash included.
    """
    return f"{rag_base_url()}{RAG_API_PREFIX}{path}"


def rag_auth_headers(access_token: str | None) -> dict[str, str]:
    """Bearer headers for a RAG call.

    The calling user's token is preferred so rag-service applies that user's
    own access rules; `INTERNAL_SERVICE_TOKEN` is the service-to-service
    fallback for work that runs without a user context. Neither present means
    no header at all rather than an empty bearer.
    """
    if access_token:
        return {"Authorization": f"Bearer {access_token}"}
    service_token = (env.INTERNAL_SERVICE_TOKEN or "").strip()
    if service_token:
        return {"Authorization": f"Bearer {service_token}"}
    return {}


def rag_timeout_seconds() -> float:
    """Per-request timeout, overridable with `RAG_HTTP_TIMEOUT_SECONDS`."""
    configured = env.RAG_HTTP_TIMEOUT_SECONDS
    if not configured:
        return _DEFAULT_TIMEOUT_SECONDS
    return float(configured)
