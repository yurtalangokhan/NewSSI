"""Pure helpers for datasource routes.

Extracted from ``DatasourcesRoute`` to keep the route file focused on endpoint
definitions.  All functions here are stateless.
"""

from __future__ import annotations

import json
from typing import Any

from models.datasources import ChunkInfo


def mask_sensitive_config(config: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive values in connector configs before returning to UI."""
    sensitive_keys = ["password", "api_key", "secret", "token", "credentials", "private_key"]
    masked: dict[str, Any] = {}
    for key, value in (config or {}).items():
        if any(s in key.lower() for s in sensitive_keys):
            masked[key] = "****"
        elif isinstance(value, dict):
            masked[key] = mask_sensitive_config(value)
        else:
            masked[key] = value
    return masked


def format_connector_name(name: str) -> str:
    """Format connector IDs for UI display labels."""
    from service.AirbyteConnectorService import _format_connector_name as _fmt

    return _fmt(name)


# Valid sync mode combinations (must match Airbyte webapp + destination spec)
VALID_SYNC_COMBOS = {
    ("full_refresh", "overwrite"),
    ("full_refresh", "append"),
    ("incremental", "append"),
}


def _truncate_doc(text: str, limit: int = 500) -> str:
    return text[:limit] + "..." if len(text) > limit else text


def _chunk_from_pg_row(sr: dict[str, Any]) -> tuple[ChunkInfo, dict[str, Any]]:
    doc_text = sr["document"] or ""
    emb_meta = sr.get("cmetadata", {}) or {}
    chunk = ChunkInfo(
        content=_truncate_doc(doc_text),
        char_count=emb_meta.get("char_count", len(doc_text)),
        token_count=emb_meta.get("token_count", max(len(doc_text.split()), int(len(doc_text) / 4))),
        word_count=emb_meta.get("word_count", len(doc_text.split())),
        source=emb_meta.get("source"),
        stream=emb_meta.get("stream"),
        connector_type=emb_meta.get("connector_type"),
        metadata=emb_meta,
    )
    sample = {"content": _truncate_doc(doc_text), "metadata": emb_meta}
    return chunk, sample


def _chunk_from_milvus_row(mr: dict[str, Any]) -> tuple[ChunkInfo, dict[str, Any]] | None:
    raw_meta = mr.get("metadata") or {}
    if isinstance(raw_meta, str):
        try:
            raw_meta = json.loads(raw_meta) if raw_meta else {}
        except Exception:
            raw_meta = {}
    if not isinstance(raw_meta, dict):
        raw_meta = {}

    doc_text = str(mr.get("text") or "")
    if not doc_text:
        return None

    chunk = ChunkInfo(
        content=_truncate_doc(doc_text),
        char_count=int(raw_meta.get("char_count", len(doc_text))),
        token_count=int(
            raw_meta.get("token_count", max(len(doc_text.split()), int(len(doc_text) / 4)))
        ),
        word_count=int(raw_meta.get("word_count", len(doc_text.split()))),
        source=raw_meta.get("source"),
        stream=raw_meta.get("stream"),
        connector_type=raw_meta.get("connector_type"),
        metadata={
            "chunk_id": str(mr.get("pk", "")),
            **raw_meta,
        },
    )
    sample = {"content": _truncate_doc(doc_text), "metadata": raw_meta}
    return chunk, sample


def build_chunk_infos(
    emb_rows: list[dict[str, Any]],
    milvus_rows: list[dict[str, Any]],
) -> tuple[list[ChunkInfo], list[dict[str, Any]]]:
    """Build ``ChunkInfo`` objects and backward-compat samples.

    Prefers PG embedding rows; falls back to Milvus rows when PG is empty
    (Milvus-backed ingestion flow).
    """
    chunks: list[ChunkInfo] = []
    samples: list[dict[str, Any]] = []

    for sr in emb_rows:
        chunk, sample = _chunk_from_pg_row(sr)
        chunks.append(chunk)
        samples.append(sample)

    if not chunks:
        for mr in milvus_rows:
            built = _chunk_from_milvus_row(mr)
            if built is None:
                continue
            chunk, sample = built
            chunks.append(chunk)
            samples.append(sample)

    return chunks, samples
