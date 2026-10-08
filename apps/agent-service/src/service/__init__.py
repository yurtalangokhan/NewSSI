"""Service layer for agent-service.

Domain Bounded Contexts:
- ``service.auth``: Authentication, permission and email configuration
- ``service.mcp``: MCP provider credentials, OAuth and tool syncing
- ``service.storage``: File storage, MinIO and document generation
- ``service.ingest``: Data sources, connector catalog and sync runtime
- ``service.runtime``: Run execution, checkpoints and scheduling
- ``service.chat``: History reconstruction, context and chat threads
- ``service.orchestration``: Agent coordination, tools and streaming
- ``service.cache``: Cross-service cache invalidation
- ``service.web_search``: Web search progress tracking
- ``service.documents``: Document and spreadsheet rendering
- ``service.reconstruction``: Chat history and flow timeline reconstruction
- ``service.stream``: Streaming infrastructure and event handling
"""

from __future__ import annotations

from service import (
    auth,
    cache,
    chat,
    documents,
    ingest,
    mcp,
    orchestration,
    reconstruction,
    runtime,
    storage,
    stream,
    web_search,
)

__all__ = [
    "auth",
    "cache",
    "chat",
    "documents",
    "ingest",
    "mcp",
    "orchestration",
    "reconstruction",
    "runtime",
    "storage",
    "stream",
    "web_search",
]
