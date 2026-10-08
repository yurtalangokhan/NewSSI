# RAG service index

Use this file only for work under `apps/rag-service/`. Root `AGENTS.md` owns the
workflow; this file routes RAG work to code, tests, and durable documentation.

## Ownership and source map

RAG service owns retrieval, document processing, vector collections, and graph
storage. Its source package is `src`, organised by **domain** — each
domain folder owns its router, service, repository, and schemas together.
Cross-cutting infrastructure lives in `shared/`, not inside any one domain.

```text
src/server.py                 FastAPI entrypoint (`APP`)
src/shared/                   Auth, config, observability, idempotency,
                                       vector-store factory, Postgres engine/models
src/collections/              Domain: collection *metadata* lifecycle
src/documents/                Domain: document/chunk CRUD, upload pipeline
src/datasources/              Domain: connector-managed collections
src/graph/                    Domain: knowledge-graph build/browse/search
src/retrieval/                Domain: unified agent-facing search
src/scripts/                  Standalone ops tooling (not imported by the app)
src/search/                            Domain: multi-collection knowledge search page
tests/unit_tests/                     Default unit-test scope
```

Each domain folder follows the same internal shape (not every domain needs
every file — `datasources/` and `retrieval/` are thin):

```text
<domain>/router.py      FastAPI routes
<domain>/service.py      Business logic
<domain>/repository.py   Typed DB I/O (where the domain owns a table directly)
<domain>/schemas.py      Pydantic models / TypedDicts for this domain
```

`search/` keeps its orchestration framework-free: `service.py` depends on
`ports.py`, `adapters.py` binds the ports to stores, and `ranking.py`,
`mapping.py`, and `facets.py` are pure.

`graph/` is the largest domain and additionally has `graph/queries/` (Cypher
strings as named constants) and `graph/repositories/` (one class per Neo4j
query concern: entities, search, stats, clustering, expansion, and the
`ScalableGraphRepository` orchestrator that composes them).

## Task routing

Use the narrowest row that matches the task.

| Change | Start in | Direct tests |
|---|---|---|
| Collection metadata (CRUD, permissions) | `src/collections/` | `tests/unit_tests/test_collections_api.py`, `test_collection_grants.py` |
| Document/chunk CRUD, upload pipeline, parsers | `src/documents/` | `tests/unit_tests/test_document*.py`, `test_collection_*.py`, `test_upload_*.py` |
| Connector-managed collections | `src/datasources/` | `tests/unit_tests/test_datasource*.py` |
| Graph build, browse, search, visualisation | `src/graph/` | `tests/unit_tests/test_graph_rag_service.py`, `test_*_repository*.py`, `test_sanitize_neo4j_value.py` |
| Unified agent-facing retrieval | `src/retrieval/` | `tests/unit_tests/test_retrieval_contract.py` |
| Knowledge search page (fan-out, fusion, facets, neighborhood) | `src/search/` | `tests/unit_tests/test_search_*.py` |
| Auth, authorization, config, idempotency, Postgres/vector-store infra | `src/shared/` | Matching unit tests |

## Documentation routing

Open only a document whose condition matches the change.

| Condition | Document |
|---|---|
| Public endpoint, model, or response changes | `docs/api.md` |
| Storage or domain boundaries change | `docs/architecture.md` |
| Test scope is unclear | `docs/testing.md` |
| Startup, environment, database, or operations change | `docs/runbook.md` |
| Service ownership is unclear | `docs/overview.md` |

## Invariants

- Each domain owns its router/service/repository/schemas together; do not
  reintroduce a cross-domain `api/`, `services/`, or `models/` layer.
- A domain may import another domain's `service`/`schemas`/`repository`
  where genuinely needed (e.g. `documents` depends on `collections` for
  collection-metadata resolution) — domains are not fully isolated, only
  co-located by concern.
- Keep Milvus, Postgres, and Neo4j connection/session code under `shared/`
  (`shared/vectorstore.py`, `shared/postgres/`) or the `graph/` domain
  (`graph/connection.py`, Neo4j is graph-specific); no domain opens its own
  ad-hoc DB connection.
- Use async I/O, Pydantic models for API schemas, and TypedDicts for internal
  shapes.
- Use the shared `ruff.toml` (line length 120, identical across Python services). Do not add redundant
  `pytest.mark.asyncio` annotations.
- Retrieval contracts crossing into tools-service require the matching
  tools-service index and shared contract.
- Read configuration only through config_manager's typed accessor
  (`from config_manager import env`); direct `os.environ`/`os.getenv` reads are
  not allowed in application code (migrations and bootstrap excepted).

## Test scope

Use `make test TEST_FILE=<path>` inside the quiet task/spec wrappers. The
default affected area is `tests/unit_tests/`; add graph, integration, or
tools-service tests only when that contract changes. Full `make validate` runs
only through the push wrapper.
