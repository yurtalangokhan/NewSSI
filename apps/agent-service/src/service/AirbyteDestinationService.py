"""
Airbyte Destination Bridge — Streaming Architecture.

With the custom ``destination-embedding`` connector, data now flows
directly from Airbyte → HTTP POST → agent-service ``/ingest/batch``.

There is **no file I/O** — the destination connector streams record
batches over the Docker network to agent-service, which embeds them
immediately into PGVector.

This module retains the ``get_destination_reader()`` factory for
backward compatibility but the reader is a no-op since data is
delivered via HTTP push, not filesystem pull.
"""

from __future__ import annotations

from core.logger import get_logger

logger = get_logger(__name__)
import logging as _stdlib_logging
logger_stdlib = _stdlib_logging.getLogger(__name__)
from typing import Any

logger = get_logger(__name__)


class EmbeddingDestinationReader:
    """No-op reader — data arrives via HTTP push from destination-embedding.

    The ``/ingest/batch`` endpoint in ``ingest_routes.py`` handles all
    record ingestion.  This class exists only for backward compatibility
    with any code that calls ``get_destination_reader()``.
    """

    async def read_sync_output(
        self,
        connection_id: str | None = None,
        job_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return empty list — data is pushed via HTTP, not pulled from files."""
        logger.info(
            "read_sync_output called but data is delivered via /ingest/batch. "
            "Nothing to read from filesystem."
        )
        return []

    async def cleanup_sync_output(
        self,
        connection_id: str | None = None,
        job_id: int | None = None,
    ) -> None:
        """No-op — there are no files to clean up."""
        pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_INSTANCE: EmbeddingDestinationReader | None = None


def get_destination_reader() -> EmbeddingDestinationReader:
    """Return the global destination reader singleton."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = EmbeddingDestinationReader()
    return _INSTANCE
