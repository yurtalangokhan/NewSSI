"""Size bounds for one KnowledgeEvidence payload.

Evidence is persisted once per retrieval call and streamed to the browser, so
every collection and text field has a ceiling. Values over a ceiling are cut,
never rejected: a long chunk must still produce a card.
"""

from __future__ import annotations

from typing import Final

SCHEMA_VERSION: Final = 1

MAX_QUERY_CHARS = 1_000
MAX_COLLECTIONS = 20
MAX_CHUNKS = 20
MAX_CHUNK_CHARS = 4_000
MAX_MODEL_CONTEXT_CHARS = 16_000
MAX_SOURCE_FIELD_CHARS = 300
MAX_GRAPH_NODES = 60
MAX_GRAPH_EDGES = 120
MAX_PROPERTIES = 20
MAX_PROPERTY_VALUE_CHARS = 500
MAX_LABEL_CHARS = 200
