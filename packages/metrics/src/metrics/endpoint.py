"""Prometheus exposition endpoint shared by every platform service."""

import os
from collections.abc import MutableMapping
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest, multiprocess
from starlette.responses import Response

from .registry import REGISTRY

#: Legacy Prometheus text format; the content type Prometheus negotiates by default.
PROMETHEUS_CONTENT_TYPE = CONTENT_TYPE_LATEST


def _active_registry() -> CollectorRegistry:
    """Return the registry to scrape, honouring gunicorn/uvicorn multi-worker mode.

    When ``PROMETHEUS_MULTIPROC_DIR`` is set, each worker writes its samples to
    shared mmap files and the scrape aggregates them; otherwise the in-process
    registry is authoritative.
    """
    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if not multiproc_dir:
        return REGISTRY

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry, path=multiproc_dir)
    return registry


def metrics_response() -> Response:
    """Render the current metrics as a Prometheus text-format response."""
    return Response(
        content=generate_latest(_active_registry()),
        media_type=PROMETHEUS_CONTENT_TYPE,
    )


async def metrics_endpoint(request: MutableMapping[str, Any] | Any) -> Response:
    """Starlette route handler wrapper around :func:`metrics_response`."""
    return metrics_response()


__all__ = ["PROMETHEUS_CONTENT_TYPE", "metrics_endpoint", "metrics_response"]
