# RAG Service (LangConnect) API

**Service:** RAG (Retrieval-Augmented Generation) — vector search, document processing, and knowledge graphs.
**Base URL:** `http://kong:8000/rag-service` (via Kong) or `http://rag-service:8083` (direct)
**Canonical API prefix:** `/api/v1`
**Auth:** JWT Bearer token, API Key, or Internal Service Token. `/api/v1/health` and `/api/v1/graph/health` are public.

RAG resolves bearer-token identity through user-service before using its local
JWT or API-key fallback. Permission checks also call user-service for
fine-grained authorization (cached 30s by default).
Compatibility aliases may remain during migration. New integrations must use
the canonical `/api/v1` paths documented here.

---

## Idempotency

Mutating rag-service endpoints use the shared idempotency model. Reusing a key
with a different request fingerprint or principal returns
`409 idempotency_key_reused`.

`domain_required` routes reject missing `Idempotency-Key` with
`400 idempotency_key_required`. This category includes graph build, graph
pause/resume/stop, document upload, graph delete, and force collection delete.
These routes can start background work, write vector or graph storage, or
perform destructive cleanup.

`required_replay` routes include collection create and collection update. They
require keys when `IDEMPOTENCY_ENFORCE_REQUIRED_KEYS=true`. Search, read-only
Cypher, normal collection delete, and other lower-risk mutations are
`optional_replay`; a supplied key enables replay and conflict detection.

---

## Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/health` | Public | `{"status": "ok"}` |

---

## Collections

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/api/v1/collections` | `collection:create` | Create vector collection (body: `name`, `metadata?`) |
| GET | `/api/v1/collections` | `collection:list` | List all collections |
| GET | `/api/v1/collections/{collection_id}` | `collection:read` | Get collection details |
| PATCH | `/api/v1/collections/{collection_id}` | `collection:update` | Update collection (name, metadata). Blocked for connector-managed or during graph builds. |
| DELETE | `/api/v1/collections/{collection_id}` | `collection:delete` | Delete collection. Blocked for connector-managed or during graph builds. |
| DELETE | `/api/v1/collections/{collection_id}/force` | `collection:delete` | Delete a collection for admin cleanup. Bypasses connector-managed read-only checks, but remains blocked during graph builds. |

---

## Datasources

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/datasources/knowledge-selector` | `datasource:read` | Categorized knowledge sources for the agent editor. Returns vector collections visible to the current user and graph collections that still have live collection metadata. |

---

## Documents

**Prefix:** `/api/v1/collections/{collection_id}/documents`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/api/v1/collections/{collection_id}/documents` | `document:create` | Upload files (multipart). Max 200 MB per file. Supported: PDF, DOCX, PPTX, CSV, XLSX, TXT, MD, HTML, JSON, RTF, EML. Chunked at 1000 chars, 200 overlap, upserted to Milvus. |
| GET | `/api/v1/collections/{collection_id}/documents` | `document:read` | List documents (query: `limit` default 10, `offset` default 0) |
| GET | `/api/v1/collections/{collection_id}/documents/{document_id}/chunks` | `document:read` | Get all chunks + stats for a document |
| DELETE | `/api/v1/collections/{collection_id}/documents/{document_id}` | `document:delete` | Delete document and all its chunks. Blocked for connector-managed or during graph builds. |
| POST | `/api/v1/collections/{collection_id}/documents/search` | `document:search` | Semantic search by vector similarity (body: `query`, `limit?`, `filter?`) |

---

## Graph RAG

**Prefix:** `/api/v1/graph`

The graph RAG subsystem builds knowledge graphs from vector collections using LLM-based entity extraction (Ollama or OpenAI), stores entities and relationships in Neo4j.

### Build pipeline

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/api/v1/graph/build` | `graph:build` | Trigger knowledge graph build from a collection (runs in background). Body: `collection_id`, `entity_types?`, `relationship_types?` |
| GET | `/api/v1/graph/build/{collection_id}/status` | `graph:read` | Get build progress (pending/extracting/building/completed/failed) |
| POST | `/api/v1/graph/build/{collection_id}/pause` | `graph:build` | Pause running build |
| POST | `/api/v1/graph/build/{collection_id}/resume` | `graph:build` | Resume paused build |
| POST | `/api/v1/graph/build/{collection_id}/stop` | `graph:build` | Cancel running build |

### Graph data

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/graph/collections` | `graph:read` | List collection IDs that have a knowledge graph |
| GET | `/api/v1/graph/collections/{collection_id}/nodes` | `graph:read` | List graph nodes (query: `limit`, `offset`, `label`) |
| GET | `/api/v1/graph/collections/{collection_id}/edges` | `graph:read` | List graph edges (query: `limit`, `offset`) |
| GET | `/api/v1/graph/collections/{collection_id}/data` | `graph:read` | Full graph data (nodes + edges) for visualization |
| GET | `/api/v1/graph/collections/{collection_id}/data/scalable` | `graph:read` | Scalable visualization (modes: auto/overview/expand/neighborhood/full) |
| GET | `/api/v1/graph/collections/{collection_id}/neighborhood` | `graph:read` | Ego-graph around a node (query: `node_id`, `depth`, `limit`) |
| GET | `/api/v1/graph/collections/{collection_id}/expand` | `graph:read` | Expand cluster to individual nodes (query: `label`) |

### Graph search

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/api/v1/graph/search` | `graph:search` | Hybrid search: vector similarity + graph traversal with RRF fusion scoring. Body: `query`, `collection_id`, `limit?`, `vector_weight?`, `graph_weight?` |
| GET | `/api/v1/graph/collections/{collection_id}/search/entities` | `graph:search` | Search entities by name (query: `q`, `limit`) |
| GET | `/api/v1/graph/collections/{collection_id}/search/entity-clusters` | `graph:search` | Lightweight cluster search for explorer |

### Graph stats

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/graph/collections/{collection_id}/stats` | `graph:read` | Graph statistics (node/edge counts, labels, relationship types) |
| GET | `/api/v1/graph/collections/{collection_id}/stats/labels` | `graph:read` | Paginated entity labels with counts |
| GET | `/api/v1/graph/collections/{collection_id}/stats/relationship-types` | `graph:read` | Paginated relationship types with counts |

### Cypher

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/api/v1/graph/cypher` | `graph:search` | Execute read-only Cypher query scoped to collection (body: `query`, `collection_id`, `parameters?`) |

### Deletion

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| DELETE | `/api/v1/graph/collections/{collection_id}` | `graph:delete` | Delete entire knowledge graph for a collection |

### Graph health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/graph/health` | Public | Neo4j connectivity check |

---

## Storage backends

| Backend | Purpose | Technology |
|---------|---------|------------|
| PostgreSQL | Collection metadata, document metadata | SQLAlchemy 2.0 async (asyncpg) |
| Milvus | Vector embeddings, similarity search | LangChain Milvus wrapper |
| Neo4j | Knowledge graph (entities, relationships) | Neo4j async driver |

## Embedding providers

| Provider | Config | Default model |
|----------|--------|---------------|
| Ollama (default) | `OLLAMA_BASE_URL`, `OLLAMA_EMBED_MODEL` | `nomic-embed-text` |
| OpenAI | fallback when provider != ollama | `text-embedding-ada-002` |

## Permission reference

| Permission | Endpoints |
|---|---|
| `collection:create`, `collection:delete`, `collection:list`, `collection:read`, `collection:update` | Collections |
| `datasource:read` | Knowledge selector |
| `document:create`, `document:delete`, `document:read`, `document:search` | Documents |
| `graph:build`, `graph:delete`, `graph:read`, `graph:search` | Graph RAG |

## Layer architecture

```
API (routers)       → Services              → Database
────────────────────────────────────────────────────────
collections.py      → CollectionsManager    → CollectionRepository (PG) + Milvus
documents.py        → process_document()    → Milvus + DocumentRepository (PG)
datasources.py      → CollectionsManager    → PG + Neo4j
graph.py            → GraphRAGService       → Neo4j repositories (Entity, Search, Stats, Visualization)
```
