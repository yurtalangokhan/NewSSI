"""
Datasource sync bookkeeping.

Sync progress shown by the datasource UI lives in the collection metadata;
this module writes it, and drives the optional Graph RAG rebuild that follows
a successful sync. The sync itself runs in ``service.ingest.connector_runtime``.
"""

import asyncio
from datetime import UTC, datetime
import time
from uuid import uuid4

from config_manager import env
from error_contract import ApplicationError, DependencyConnectionError, render_error_message
import httpx

from core.http import outbound
from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import datasource_repository
from integrations.rag_client import get_graph_build_progress, trigger_graph_build


def _get_rag_service_base_url() -> str:
    """rag-service's root for this module's graph-build routes.

    Reads ``env.INTERNAL_RAG_SERVICE_API_URL`` rather than ``core.http.rag_http``
    on purpose: this module is tracked debt in
    ``tests/architecture/test_rag_client_is_the_only_boundary_architecture.py``
    (the ``/api/graph/build`` routes it calls sit outside the typed client's
    contract), and that boundary test forbids a non-owner from importing the
    transport's URL builders. The accessor already strips the trailing slash.
    """
    base_url = env.INTERNAL_RAG_SERVICE_API_URL
    if not base_url:
        raise RuntimeError("INTERNAL_RAG_SERVICE_API_URL must be configured")
    return base_url


logger = get_logger(__name__)


# ------------------------------------------------------------------
# Graph RAG availability check (cached)
# ------------------------------------------------------------------

_graph_rag_cache: dict = {"available": False, "checked_at": 0.0}
_GRAPH_RAG_CACHE_TTL = 300  # seconds


async def is_graph_rag_available() -> bool:
    """Check whether the RAG service graph API is reachable.

    The result is cached for ``_GRAPH_RAG_CACHE_TTL`` seconds so that
    every details request does not incur a network round-trip.
    """
    now = time.time()
    if now - _graph_rag_cache["checked_at"] < _GRAPH_RAG_CACHE_TTL:
        return _graph_rag_cache["available"]

    try:
        resp = await outbound.request(
            outbound.RAG_SERVICE,
            "GET",
            f"{_get_rag_service_base_url()}/docs",
            timeout=httpx.Timeout(3.0),
        )
        available = resp.status_code < 500
    except Exception:
        available = False

    _graph_rag_cache["available"] = available
    _graph_rag_cache["checked_at"] = now
    return available


async def update_sync_status(uuid_str: str, status: str, error_msg: str | None):
    """Update final sync status with timestamp."""
    now = datetime.now(UTC).isoformat()

    ds_repo = datasource_repository()
    row = await ds_repo.get_collection(uuid_str)
    if not row:
        return

    meta = row.get("cmetadata", {})
    meta["sync_status"] = status
    meta["sync_progress"] = 100 if status == "completed" else 0
    meta["last_synced_at"] = now

    if error_msg:
        meta["last_error"] = error_msg
    else:
        meta.pop("last_error", None)

    await ds_repo.update_collection_metadata(uuid_str, meta)


async def update_sync_progress(uuid_str: str, stage: str, progress: int):
    """Update sync progress for real-time tracking."""
    ds_repo = datasource_repository()
    row = await ds_repo.get_collection(uuid_str)
    if not row:
        return

    meta = row.get("cmetadata", {})
    meta["sync_status"] = stage
    meta["sync_progress"] = progress

    await ds_repo.update_collection_metadata(uuid_str, meta)


# ------------------------------------------------------------------
# Graph RAG rebuild via the typed rag-service client
# ------------------------------------------------------------------


def graph_build_idempotency_key(datasource_id: str, run_id: str | None = None) -> str:
    """The idempotency key of one graph build.

    ``run_id`` (the sync job that asked for the rebuild) scopes the key, so a
    retry of the same request replays while the next sync gets a fresh build.
    rag-service accepts letters, digits, ".", "_" and "-" in a key, nothing else.
    """
    return f"graph-build.{datasource_id}.{run_id or uuid4().hex}"


async def trigger_graph_rag_rebuild(datasource_id: str, run_id: str | None = None) -> None:
    """Call RAG's versioned JSON graph-build client to rebuild the knowledge graph.

    Updates cmetadata with graph_update_status for UI feedback. ``run_id`` (the
    sync job that asked for the rebuild) scopes the idempotency key, so a retry
    of the same request replays while the next sync gets a fresh build.
    """
    logger.info("Triggering Graph RAG rebuild for %s", datasource_id)
    await _update_graph_status(datasource_id, "graph_rebuilding")

    try:
        build_data = await trigger_graph_build(
            datasource_id, idempotency_key=graph_build_idempotency_key(datasource_id, run_id)
        )
        logger.info("Graph build triggered for %s: %s", datasource_id, build_data.get("status"))

        # 2. Poll build progress until complete
        max_polls = 600  # 10 min max (1s interval)
        for _ in range(max_polls):
            await asyncio.sleep(1.0)
            progress = await get_graph_build_progress(datasource_id)
            if progress is None:
                continue
            current_status = progress.get("status", "")

            if current_status == "completed":
                logger.info("Graph RAG rebuild completed for %s", datasource_id)
                await _update_graph_status(datasource_id, "graph_completed")
                return
            elif current_status == "failed":
                err = progress.get("error", "Unknown graph build error")
                logger.error("Graph RAG rebuild failed for %s: %s", datasource_id, err)
                await _update_graph_status(datasource_id, "graph_failed", err)
                return

        # Timed out
        logger.warning("Graph RAG rebuild timed out for %s", datasource_id)
        await _update_graph_status(datasource_id, "graph_timeout")

    # ``rag_client`` never lets an ``httpx`` exception through: an enveloped answer is an
    # ``ApplicationError`` with rag-service's status and code, and a transport failure
    # arrives as one of the ``Dependency*Error`` subclasses ``outbound.request`` raises.
    except DependencyConnectionError:
        logger.warning(
            "Graph RAG service not reachable at %s for datasource %s - skipping graph rebuild",
            _get_rag_service_base_url(),
            datasource_id,
        )
        await _update_graph_status(datasource_id, "graph_unavailable")
    except ApplicationError as exc:
        logger.error("Graph RAG rebuild failed for %s: %s %s", datasource_id, exc.status_code, exc.code)
        await _update_graph_status(datasource_id, "graph_failed", render_error_message(exc))
    except Exception as exc:
        logger.exception("Graph RAG rebuild error for %s", datasource_id)
        await _update_graph_status(datasource_id, "graph_failed", str(exc))


async def _update_graph_status(uuid_str: str, graph_status: str, error: str | None = None) -> None:
    """Write graph_update_status into cmetadata for UI feedback."""
    ds_repo = datasource_repository()
    row = await ds_repo.get_collection(uuid_str)
    if not row:
        return

    meta = row.get("cmetadata", {})
    meta["graph_update_status"] = graph_status
    if error:
        meta["graph_update_error"] = error
    else:
        meta.pop("graph_update_error", None)

    await ds_repo.update_collection_metadata(uuid_str, meta)
