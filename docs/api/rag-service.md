# RAG Service (LangConnect) API

**Service:** RAG (Retrieval-Augmented Generation) — vector search, document processing, and knowledge graphs.
**Base URL:** `http://kong:8000` (via Kong, path `/api/rag/*`) or `http://rag-service:8083` (direct)
**Auth:** JWT Bearer token, API Key, or Internal Service Token. `/health` is public.

Permission checks call user-service for fine-grained authorization (cached 30s by default).

---

## Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | Public | `{"status": "ok"}` |

---

## Collections

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/collections` | `collection:create` | Create vector collection (body: `name`, `metadata?`) |
| GET | `/collections` | `collection:list` | List all collections |
| GET | `/collections/{collection_id}` | `collection:read` | Get collection details |
| PATCH | `/collections/{collection_id}` | `collection:update` | Update collection (name, metadata). Blocked for connector-managed or during graph builds. |
| DELETE | `/collections/{collection_id}` | `collection:delete` | Delete collection. Blocked for connector-managed or during graph builds. |

---

## Datasources

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/datasources/knowledge-selector` | `datasource:read` | Categorized knowledge sources for agent editor (vector + graph collections) |

---

## Documents

**Prefix:** `/collections/{collection_id}/documents`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/collections/{collection_id}/documents` | `document:create` | Upload files (multipart). Max 200 MB per file. Supported: PDF, DOCX, PPTX, CSV, XLSX, TXT, MD, HTML, JSON, RTF, EML. Chunked at 1000 chars, 200 overlap, upserted to Milvus. |
| GET | `/collections/{collection_id}/documents` | `document:read` | List documents (query: `limit` default 10, `offset` default 0) |
| GET | `/collections/{collection_id}/documents/{document_id}/chunks` | `document:read` | Get all chunks + stats for a document |
| DELETE | `/collections/{collection_id}/documents/{document_id}` | `document:delete` | Delete document and all its chunks. Blocked for connector-managed or during graph builds. |
| POST | `/collections/{collection_id}/documents/search` | `document:search` | Semantic search by vector similarity (body: `query`, `limit?`, `filter?`) |

---

## Graph RAG

**Prefix:** `/graph`

The graph RAG subsystem builds knowledge graphs from vector collections using LLM-based entity extraction (Ollama or OpenAI), stores entities and relationships in Neo4j.

### Build pipeline

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/graph/build` | `graph:build` | Trigger knowledge graph build from a collection (runs in background). Body: `collection_id`, `entity_types?`, `relationship_types?` |
| GET | `/graph/build/{collection_id}/status` | `graph:read` | Get build progress (pending/extracting/building/completed/failed) |
| POST | `/graph/build/{collection_id}/pause` | `graph:build` | Pause running build |
| POST | `/graph/build/{collection_id}/resume` | `graph:build` | Resume paused build |
| POST | `/graph/build/{collection_id}/stop` | `graph:build` | Cancel running build |

### Graph data

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/graph/collections` | `graph:read` | List collection IDs that have a knowledge graph |
| GET | `/graph/collections/{collection_id}/nodes` | `graph:read` | List graph nodes (query: `limit`, `offset`, `label`) |
| GET | `/graph/collections/{collection_id}/edges` | `graph:read` | List graph edges (query: `limit`, `offset`) |
| GET | `/graph/collections/{collection_id}/data` | `graph:read` | Full graph data (nodes + edges) for visualization |
| GET | `/graph/collections/{collection_id}/data/scalable` | `graph:read` | Scalable visualization (modes: auto/overview/expand/neighborhood/full) |
| GET | `/graph/collections/{collection_id}/neighborhood` | `graph:read` | Ego-graph around a node (query: `node_id`, `depth`, `limit`) |
| GET | `/graph/collections/{collection_id}/expand` | `graph:read` | Expand cluster to individual nodes (query: `label`) |

### Graph search

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/graph/search` | `graph:search` | Hybrid search: vector similarity + graph traversal with RRF fusion scoring. Body: `query`, `collection_id`, `limit?`, `vector_weight?`, `graph_weight?` |
| GET | `/graph/collections/{collection_id}/search/entities` | `graph:search` | Search entities by name (query: `q`, `limit`) |
| GET | `/graph/collections/{collection_id}/search/entity-clusters` | `graph:search` | Lightweight cluster search for explorer |

### Graph stats

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/graph/collections/{collection_id}/stats` | `graph:read` | Graph statistics (node/edge counts, labels, relationship types) |
| GET | `/graph/collections/{collection_id}/stats/labels` | `graph:read` | Paginated entity labels with counts |
| GET | `/graph/collections/{collection_id}/stats/relationship-types` | `graph:read` | Paginated relationship types with counts |

### Cypher

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/graph/cypher` | `graph:search` | Execute read-only Cypher query scoped to collection (body: `query`, `collection_id`, `parameters?`) |

### Deletion

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| DELETE | `/graph/collections/{collection_id}` | `graph:delete` | Delete entire knowledge graph for a collection |

### Graph health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/graph/health` | Public | Neo4j connectivity check |

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
| `document:create`, `document:delete`, `document:read`, `document:search`, `document:update` | Documents |
| `graph:build`, `graph:delete`, `graph:read`, `graph:search` | Graph RAG |
| `chunk:read`, `chunk:search` | Chunks |
| `embedding:read` | Embeddings |

## Layer architecture

```
API (routers)       → Services              → Database
────────────────────────────────────────────────────────
collections.py      → CollectionsManager    → CollectionRepository (PG) + Milvus
documents.py        → process_document()    → Milvus + DocumentRepository (PG)
datasources.py      → CollectionsManager    → PG + Neo4j
graph.py            → GraphRAGService       → Neo4j repositories (Entity, Search, Stats, Visualization)
```
