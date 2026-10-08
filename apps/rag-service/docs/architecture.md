# RAG service architecture

RAG service is organised by **domain**, not by technical layer. Each domain
(`collections`, `documents`, `datasources`, `graph`, `retrieval`, `search`) owns its
router, service, and — where it owns a table directly — repository and
schemas together in one folder, instead of a cross-cutting `api/`/`services/`/
`database/`/`models/` split. Cross-cutting infrastructure (auth, config,
observability, idempotency, the Postgres engine/models, the Milvus/PGVector
vector-store factory) lives in `shared/`, which every domain may depend on but
which depends on no domain.

## Data flow

```text
src/<domain>/router.py -> src/<domain>/service.py -> src/<domain>/repository.py | src/shared/
```

Document upload and ingestion write vector chunks to Milvus (`documents`
domain, via `shared/vectorstore.py`) and collection metadata to Postgres
(`collections` domain). Graph build operations (`graph` domain) extract
entities and relationships, then write graph data to Neo4j through
`graph/repositories/`.

Domains are not fully isolated — they are co-located by concern, and one
domain importing another's `service`/`schemas`/`repository` is expected where
the underlying resource is genuinely shared. In particular:

- `documents` depends on `collections` to resolve collection metadata (which
  Milvus table a document's collection maps to, and permission checks).
- `datasources` depends on both `collections` and `documents` (a
  connector-managed collection is still a collection with documents in it).
- `graph` depends on `documents` for the `Collection.ensure_exists` /
  `fetch_all_chunks` calls a graph build reads chunks through.
- `retrieval` depends on `collections`, `documents`, and `graph` to fuse
  vector and graph search behind one endpoint. Its per-collection store
  adapters live in `retrieval/adapters.py` so other domains reuse them.
- `search` depends on `retrieval` (contract and adapters), `collections`
  (readable collections and display names), `documents`, and `graph`. It runs
  the retrieval contract for every readable collection and fuses the results
  for the web knowledge search page.

## Knowledge search boundary

The web knowledge search page calls `POST /api/v1/search`,
`GET /api/v1/search/sources`, and `POST /api/v1/search/graph/neighborhood`
through the gateway. `search/service.py` is framework-free: it depends only on
the ports in `search/ports.py`, and `search/router.py` composes the store
adapters from `search/adapters.py`. Ranking (`ranking.py`), hit mapping
(`mapping.py`), and facets (`facets.py`) are pure functions.

## Retrieval boundary

Agent-facing retrieval is exposed through tools-service. Tools-service calls
rag-service `POST /api/v1/retrieval` with trusted user and tenant context. Keep
new reusable agent tools in tools-service, and keep retrieval implementation in
rag-service.
