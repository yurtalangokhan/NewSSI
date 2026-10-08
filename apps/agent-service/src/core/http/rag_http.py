"""The transport contract for agent-service -> rag-service calls.

Every RAG call needs the same three decisions: which base URL, which bearer
token, how long to wait. Those decisions were previously re-made at each call
site, and the copies had drifted into three different fallbacks. Keeping them
here means a deployment change is one edit, and a new call site cannot invent
a fourth opinion.

`INTERNAL_RAG_SERVICE_API_URL` is the internal service setting. An
unconfigured deployment fails loudly rather than silently calling localhost.

It lives in `core/` rather than `integrations/` because `domain/` needs it —
`service/flows/resolvers.py` builds its URLs with :func:`rag_url` — and the
architecture gate (docs/oop-solid-architecture.md) forbids `domain/` from
importing `integrations`. Nothing here is an adapter: it is transport policy,
the same kind `core/http/outbound.py` owns.
"""

from __future__ import annotations

from config_manager import env
from security import timeout_for

# Shared REST prefix every rag-service route sits under.
RAG_API_PREFIX = "/api/v1"


def rag_base_url() -> str:
    """rag-service's root, without a trailing slash."""
    configured = env.INTERNAL_RAG_SERVICE_API_URL
    if not configured:
        raise RuntimeError("INTERNAL_RAG_SERVICE_API_URL must be configured")
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
    """Per-request timeout, overridable with `RAG_HTTP_TIMEOUT_SECONDS`.

    Without the override the value comes from `configs/resilience.yaml`, where a
    `dependencies.rag-service.timeoutSeconds` entry takes precedence over the
    shared default.
    """
    configured = env.RAG_HTTP_TIMEOUT_SECONDS
    if configured:
        return float(configured)
    return timeout_for("rag-service")


def rag_ingest_timeout_seconds() -> float:
    """Budget for one connector-ingest request (`dependencies.rag-service-ingest`).

    rag-service splits and embeds the whole batch inside the request, which takes
    minutes on a local embedding model; the chat budget above would cut it off and
    the retry would re-post the batch. No environment override: the file is the
    single place this policy lives.
    """
    return timeout_for("rag-service-ingest")
