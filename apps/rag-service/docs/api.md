# RAG Service API

**Service:** RAG (Retrieval-Augmented Generation) — vector search, document processing, and knowledge graphs.
**Gateway base:** `/rag-service` through APISIX.
**Canonical API prefix:** `/api/v1`
**Auth:** Gateway-established user or internal identity. Health is public.

This is the human-maintained endpoint contract for rag-service. Prefer
generated OpenAPI output only when you need schema-level detail or client
generation.

Gateway authenticates callers and forwards their trusted identity. RAG resolves
that identity and asks user-service for action and resource permissions.
New integrations use the canonical `/api/v1` paths documented here.

## JSON response contract

All 41 application JSON endpoints return the service-local `ResponseModel[T]`.
The original domain payload is under `data`; `statusCode` matches the real HTTP
status. `message` is nullable and `error` is either null or an object containing
`code` and a localized `message`. Shared exceptions use central
error_contract EN/TR keys and propagate through service, controller, and
route. Dependency/auth failures, invalid requests, idempotency rejections, and
unexpected failures use the same fields.

Collection create returns HTTP 201; upload-job start returns HTTP 202. Collection
and graph deletes return HTTP 200 with `data: null`. Idle graph/upload polling
also returns null data. Health, graph-health, and readiness keep their native
payloads; failed readiness returns HTTP 503 with top-level dependency details.
Raw Prometheus metrics retain
their text transport. File, streaming, and socket transports are outside this
JSON migration.

Browser knowledge APIs validate the envelope before unwrapping data; agent
RAG clients do the same for arrays, objects, and idle nulls. The generic RAG
BFF proxy forwards transport responses unchanged. Ingestion graph builds use
the versioned RAG client and supply the required idempotency key.

Runtime regression checks remain pending; static checks are tracked in the
[shared migration checklist](../../../docs/response-model-migration.md).

Collection discovery and retrieval include direct user and organization grants
resolved by user-service for the authenticated identity. The knowledge selector
shows granted collections in document processing and, when built, knowledge
graphs. Owners and existing ingestion-visible collections remain readable.
Permission-service failures grant no additional access.

Resource access is checked in addition to each endpoint's action permission.
Document and graph reads require `read`; uploads, document mutations, collection
updates, and graph builds require `write`; collection and graph deletion require
`admin`. Read access does not permit mutations. Missing or inaccessible collection
IDs return `404`; agent retrieval rejects inaccessible collections with `403`.
Collection deletion returns an idempotent HTTP 200 JSON acknowledgement for inaccessible
or missing collections and performs no deletion without resource authorization.
Raw Cypher additionally requires authoritative system or enterprise administrator
status because arbitrary queries cannot enforce a single collection's scope.

Internal calls to `/api/v1/retrieval` must supply a nonblank `x-user-id` for
the delegated user. The `internal-service` and `dev-user` identities cannot be
delegated. This requirement applies to every accepted internal authentication
header. Public callers always use their authenticated identity; forwarded user
headers do not override it. Permission requests use the configured user-service
API prefix, including its API version.

---

## Idempotency

Mutating rag-service endpoints use the shared idempotency model. Reusing a key
with a different request fingerprint or principal returns
`409 idempotency_key_reused`.

`domain_required` routes reject missing `Idempotency-Key` with
`400 idempotency_key_required`. This category includes graph build, graph
pause/resume/stop, document upload, connector-managed datasource record
ingestion, graph delete, and force collection delete. These routes can start
background work, write vector or graph storage, or perform destructive
cleanup.

Connector-managed datasource record ingestion also sets `rerun_after_failure`:
a write that answered `429` or `5xx`, or raised, frees its key, so a retry with
the same key runs again instead of answering `409`. A write that succeeded is
still replayed, and a write in flight still answers
`409 idempotency_request_in_progress`.

`required_replay` routes include collection create and collection update. They
require keys by default (`IDEMPOTENCY_ENFORCE_REQUIRED_KEYS=true`). Search,
read-only Cypher, normal collection delete, and other lower-risk mutations are
`optional_replay`; a supplied key enables replay and conflict detection.

---

## Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/health` | Public | `{"status": "ok"}` |
| GET | `/api/v1/health/ready` | Public | Dependency readiness; HTTP 503 on failure |

---

## Collections

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/api/v1/collections` | `collection:create` | Create vector collection (body: `name`, `metadata?`) |
| GET | `/api/v1/collections` | `collection:list` | List all collections |
| GET | `/api/v1/collections/{collection_id}` | `collection:read` | Get collection details |
| PATCH | `/api/v1/collections/{collection_id}` | `collection:update` | Update collection (name, metadata). Blocked for connector-managed or during graph builds. |
| DELETE | `/api/v1/collections/{collection_id}` | `collection:delete` | Delete a collection and its Milvus table. Blocked for connector-managed or during graph builds; a failing table drop (503) keeps the collection, so the call can be repeated. |
| DELETE | `/api/v1/collections/{collection_id}/force` | `collection:delete` | Delete a collection and its Milvus table for admin cleanup. Bypasses connector-managed read-only checks, but remains blocked during graph builds. |

---

## Datasources

These JSON endpoints use the service-local `ResponseModel[T]`.
The route calls the domain controller, which calls the domain service.

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/v1/datasources/knowledge-selector` | `datasource:read` | Categorized knowledge sources for the agent editor. Returns vector collections visible to the current user and graph collections that still have live collection metadata. |
| POST | `/api/v1/datasources/{collection_id}/records` | `datasource:sync` | Chunk, embed, and store one batch of connector-synced records. Called by agent-service's connector runtime only. |
| POST | `/api/v1/datasources/{collection_id}/records/retire` | `datasource:sync` | Keep the chunks of one sync run and remove every other chunk: the end of an `overwrite` sync. Connector runtime only. |
| DELETE | `/api/v1/datasources/{collection_id}/records` | `datasource:sync` | Drop every chunk of a datasource (its Milvus table): agent-service calls it while it deletes the datasource. |
| GET | `/api/v1/datasources/{collection_id}/entities` | `datasource:read` | Read raw connector entities, counts, and optional statistics. |

A selector success returns HTTP 200 with the original payload under `data`:

```json
{
  "statusCode": 200,
  "message": null,
  "data": {"document_processing": [], "knowledge_graph": []},
  "error": null
}
```

A missing or inaccessible collection raises shared `CollectionNotFoundError`.
The service exception uses `errors.collection.not_found` from error_contract's
locale files. The route renders the request language and returns HTTP 404:

```json
{
  "statusCode": 404,
  "message": "Collection not found or inaccessible.",
  "data": null,
  "error": {
    "code": "collection.not_found",
    "message": "Collection not found or inaccessible."
  }
}
```

Frontend domain functions and agent-service's RAG client check the status and
unwrap `data`. Authentication and request validation raised before the route
body still use the global error envelope during this migration. Follow the
[platform checklist](../../../docs/response-model-migration.md) for remaining
route and transport work.

### Record ingestion

```json
{
  "documents": [
    {"content": "id: 7\ntitle: Invoice", "metadata": {"stream": "invoices"},
     "record_key": "3f786850e387550fdab836ed7e6dc881de23001b"}
  ],
  "clear_existing": false
}
```

- `documents[].record_key` (optional, `^[0-9a-f]{40}$`) names the record at its
  source. The service writes it to `metadata._record_key` of every chunk of
  the document, overwriting a value the caller sent there, and keeps one
  version per key: the new chunks are inserted, then the chunks an earlier
  write stored under the same key are deleted. A document without a key is
  appended. Of two documents with the same key in one request, the last is
  stored. A keyed document that yields no chunk still removes its earlier
  version.
- `clear_existing` deletes every chunk of the collection before the write.
- `data`: `{"chunks_indexed", "chunk_char_total", "chunk_token_total",
  "chunks_replaced"}`. `chunks_replaced` is the number of deleted chunks.
- `503 datasource.replace_failed` means Milvus failed while the earlier
  versions were looked up (nothing was written) or deleted (the new chunks
  are stored next to the old ones); the failed stage is in the service log,
  not in the envelope. Send the same request again; it finds both versions
  and leaves the new one. Documents without a key are appended again by such
  a retry.
- Chunks stored before record keys existed carry no `_record_key` and are
  never replaced; `clear_existing` removes them.

### Retiring earlier runs

`POST /api/v1/datasources/{collection_id}/records/retire` with
`{"keep_job_id": "<sync job id>"}` (`^[A-Za-z0-9_-]{1,128}$`) deletes every
chunk whose `metadata._sync_job_id` is missing or differs from `keep_job_id`,
and answers `{"chunks_removed": n}`. agent-service's connector runtime tags
every document it sends with `metadata._sync_job_id` and calls this once at the
end of an `overwrite` sync, so the previous version of the collection stays
searchable while the new one is written and a failed run leaves it in place.
An `Idempotency-Key` is optional (the call is idempotent by itself; a key only
replays the answer). Milvus failures are reported like those of the records
route (`503 datasource.replace_failed`).

### Deleting a datasource's records

`DELETE /api/v1/datasources/{collection_id}/records` drops the Milvus table of
the collection and answers `{"chunks_removed": n}`. `n` is Milvus' entity
statistic of the table (`num_entities`), which counts flushed segments only: it
is `0` when nothing was ever written and also for data Milvus has not flushed
yet, so a small or very recent collection can report fewer chunks than it held;
the table is dropped either way. agent-service calls it while it deletes a
datasource, before it deletes the collection row that names the table; when
the call fails, agent-service deletes nothing, so the delete can be repeated.
Milvus failures surface as the database errors of the collection routes.

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

## Knowledge search

The knowledge search page in the web app uses these routes to search every
collection you can read in one request. The search fans out to vector search
and, where a collection has a knowledge graph, to graph search. It fuses the
ranked lists and returns hits, the matched subgraph, and facets.

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/api/v1/search` | `document:search` (+ `graph:search` for `graph`) | Fused multi-collection search. Body: `query`, `kind?` (`hybrid` default, `vector`, `graph`), `limit?` (1-100, default 50), `collection_ids?`, `file_types?`, `entity_labels?` |
| GET | `/api/v1/search/sources` | `document:search` | Collections you can search, with `source_type` (`document` or `connector`), `connector_type`, `sync_status`, and `has_graph` |
| POST | `/api/v1/search/graph/neighborhood` | `graph:read` + collection `read` | Merged ego graph around up to 20 nodes of one collection. Body: `collection_id`, `node_ids`, `depth?` (1-3), `limit?` (1-300, default 100) |

`POST /api/v1/search` behaves as follows:

- **Ranking:** Vector scores are store-native (Milvus defaults to L2
  distance), so they aren't comparable across collections. The service fuses
  one ranked list per collection and source with Reciprocal Rank Fusion
  (k=60). `relevance` is each hit's fused score divided by the best one, so
  the top hit is `1.0`. `score` keeps the store-native value.
- **Hits:** A `document` hit carries the passage and its `source`, `title`,
  `page`, `section`, `file_id`, and `file_type` (the source extension). An
  `entity` hit is a node the query matched directly, with up to three
  `relations` and its `neighbor_count`. Expanded neighbors appear only in
  `graph`.
- **Facets and filters:** `facets` and the per-collection counts in
  `collections` cover all hits before filtering. `collection_ids` then
  filters every hit. `file_types` and `entity_labels` each describe one kind
  of hit, so choosing one asks for that kind only: a file type keeps matching
  document hits and drops every entity hit, and an entity label keeps
  matching entity hits and drops every document hit. With both, each kind
  keeps its own matches. `entity_labels` and `collection_ids` also narrow
  `graph` to the nodes with those labels in those collections, dropping edges
  that lose an endpoint. `total` counts the filtered hits; `hits` holds at
  most `limit` of them.
- **Graph permission:** `kind: graph` without `graph:search` returns `403`.
  `hybrid` without it searches vectors only and returns
  `graph_available: false`.
- **Graph store outage:** When the graph store is unreachable, `hybrid`
  searches vectors only and returns `graph_available: false` and
  `graph_unavailable: true`, so clients can tell an outage from a search with
  no graph. `graph_unavailable` is an additive field that is `false`
  otherwise and for `vector` searches.
- **Resilience:** When one collection's vector or graph store fails, the rest
  still answer and that collection reports `status: "failed"`. Only store
  and domain errors are isolated this way; other errors return `500`.

`graph` holds at most 200 nodes and 400 edges, keeping matched nodes first.
Secret-like metadata and properties are redacted as in `/api/v1/retrieval`.

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
| `document:create`, `document:delete`, `document:read`, `document:search` | Documents, knowledge search |
| `graph:build`, `graph:delete`, `graph:read`, `graph:search` | Graph RAG, knowledge search graph and neighborhood |

| `memory:search`, `memory:write` | Internal memory index |

The memory index routes under `/api/v1/memory` are available through the
internal gateway path only. User-service writes facts, and agent-service
searches them with a delegated user ID. Browser requests to the public
`/rag-service/api/v1/memory` path are denied by the gateway.

## Memory and retrieval response models

These internal JSON endpoints use the same local `ResponseModel` as datasources.
Routes call their domain controllers, which delegate to framework-free services.

| Method | Path | Data |
| --- | --- | --- |
| POST | `/api/v1/memory/facts` | `null` after indexing a fact |
| DELETE | `/api/v1/memory/facts/{fact_id}` | `null` after removing a fact |
| DELETE | `/api/v1/memory/facts` | `null` after clearing the user's index |
| POST | `/api/v1/memory/search` | The existing `{hits: [...]}` object |
| POST | `/api/v1/retrieval` | The existing kind, collection_id, hits, and context object |

Memory writes now return HTTP 200 with a JSON acknowledgement, replacing the
previous bodyless HTTP 204 response:

```json
{"statusCode": 200, "message": null, "data": null, "error": null}
```

Shared error_contract classes cover delegation, trusted identity, graph
permission, collection access, required fields, and memory write/delete errors.
Their locale keys render according to `X-Language`. The existing
`ForbiddenTrustedFieldError` covers reserved model arguments with HTTP 400.
Services never expose driver messages in public responses.

User-service parses memory acknowledgements. Agent-service unwraps memory hits.
Tools-service unwraps retrieval context and retains a stable `code` alongside
the localized tool error. Memory recall continues with empty hits when the index
is unavailable; background indexing failures remain visible to their callers.

## Layer architecture

```
Domain            Router          → Service                  → Repository / store
──────────────────────────────────────────────────────────────────────────────────
collections/      router.py       → CollectionsManager        → CollectionRepository (Postgres)
documents/        router.py       → Collection, process_document() → Milvus (shared/vectorstore.py)
datasources/      router.py       → controller.py → service.py → Postgres + Milvus
graph/            router.py       → GraphRAGService            → EntityRepository, SearchRepository,
                                                                  StatsRepository, ClusterRepository,
                                                                  ExpansionRepository, ScalableGraphRepository (Neo4j)
memory/           router.py       → controller.py → MemoryIndexService → memory.repository
retrieval/        router.py       → controller.py → RetrievalService → vector/graph ports (retrieval/adapters.py:
                                                                  documents.Collection + graph.GraphRAGService)
search/           router.py       → KnowledgeSearchService     → search ports (search/adapters.py: collections,
                                                                  RetrievalService.retrieve_authorized per collection, GraphStore)
```

`POST /api/v1/retrieval` is the additive agent-facing retrieval contract
(vector / graph / hybrid). Existing document and graph search routes are
unchanged. Collection access is authorized from trusted user identity, not
from model-visible arguments.

The response carries these fields; `context` numbering, `collection_name`, and
`graph` are additive, so clients that ignore unknown fields keep working:

- `hits` — ranked vector chunks and/or graph entities, with redacted metadata.
- `context` — the text handed to a model: numbered vector hits
  (`[n] (source)\ncontent`) and/or the graph context, joined for `hybrid`.
- `collection_name` — the searched collection's display name.
- `graph` — for `graph`/`hybrid`, the closed subgraph behind the context:
  `nodes` (`matched` marks direct query hits, `score` is the fused RRF score)
  and `edges`. Every edge endpoint is one of `nodes`; secret-like properties
  are redacted.

`POST /api/v1/graph/search` returns `seed_node_ids` alongside `nodes` and
`edges`: the ids of the nodes the query matched directly, in rank order.
