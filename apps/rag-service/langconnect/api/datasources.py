"""Datasources API — knowledge selector endpoint.

Provides a unified view of available knowledge sources for the agent editor,
combining document-processing collections (Milvus vector search) with knowledge-graph
collections (Neo4j).
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from langconnect.auth import AuthenticatedUser, require_permission
from langconnect.database.collections import CollectionsManager
from langconnect.database.neo4j import GraphStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasources", tags=["datasources"])


@router.get("/knowledge-selector")
async def knowledge_selector(
    user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:read"))],
) -> dict[str, list[dict[str, Any]]]:
    """Return categorised knowledge sources for the agent editor.

    Returns two lists:
    - ``document_processing``: all Milvus-backed collections (vector similarity search)
    - ``knowledge_graph``: collections that have a built knowledge graph in Neo4j
    """
    # 1. Fetch all vector collections (use internal identity to bypass owner filter)
    all_collections = await CollectionsManager("internal-service").list()

    def _normalize_collection_name(
        col: dict[str, Any], metadata: dict[str, Any]
    ) -> str:
        """Return a user-friendly collection name with safe fallbacks."""
        candidate = (
            metadata.get("friendly_name")
            or metadata.get("name")
            or col.get("name")
            or ""
        )
        normalized = str(candidate).strip()
        if normalized.lower() in {"", "unnamed", "datasource label"}:
            return f"datasource-{col['uuid'][:8]}"
        return normalized

    def _build_item(col: dict[str, Any]) -> dict[str, Any]:
        metadata = col.get("metadata") or {}
        return {
            "id": col["uuid"],
            "name": _normalize_collection_name(col, metadata),
            "connector_type": metadata.get("connector_type", ""),
            "sync_status": metadata.get("sync_status", "idle"),
        }

    document_processing = [_build_item(col) for col in all_collections]
    # Keep connector-backed datasources first so they are easier to find in agent setup.
    document_processing.sort(
        key=lambda item: (
            item.get("connector_type", "") == "",
            item.get("name", "").lower(),
        )
    )

    # 2. Fetch collection IDs that have a built knowledge graph
    knowledge_graph: list[dict[str, Any]] = []
    try:
        graph_collection_ids: list[str] = await GraphStore.list_graph_collection_ids()

        # Build a lookup for collection details
        col_lookup = {col["uuid"]: col for col in all_collections}

        for cid in graph_collection_ids:
            col = col_lookup.get(cid)
            if col:
                knowledge_graph.append(_build_item(col))
            else:
                # Collection exists in Neo4j but not in vector collections (orphan)
                knowledge_graph.append(
                    {
                        "id": cid,
                        "name": cid,
                        "connector_type": "",
                        "sync_status": "idle",
                    }
                )
    except Exception:
        logger.warning("Neo4j is not available — knowledge_graph list will be empty.")

    return {
        "document_processing": document_processing,
        "knowledge_graph": knowledge_graph,
    }
