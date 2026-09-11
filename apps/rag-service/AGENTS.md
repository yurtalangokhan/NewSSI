# RAG service index

Use this file only for work under `apps/rag-service/`. Root `AGENTS.md` owns the
workflow; this file routes RAG work to code, tests, and durable documentation.

## Ownership and source map

RAG service owns retrieval, document processing, vector collections, and graph
storage. Its package name is `langconnect`.

```text
langconnect/server.py                 FastAPI entrypoint (`APP`)
langconnect/api/                      Routers
langconnect/services/                 Business logic and retrieval contracts
langconnect/database/connection.py    Vector-store factory
langconnect/database/postgres/        SQLAlchemy storage and repositories
langconnect/database/neo4j/           Graph storage
langconnect/models/                   Pydantic models and TypedDicts
langconnect/auth*.py                  Authentication boundaries
langconnect/authorization.py          Authorization
langconnect/idempotency.py            Idempotency
tests/unit_tests/                     Default unit-test scope
```

## Task routing

Use the narrowest row that matches the task.

| Change | Start in | Direct tests |
|---|---|---|
| API or model | `langconnect/api/`, `langconnect/models/` | Matching `tests/unit_tests/` route tests |
| Retrieval | `langconnect/services/` | Retrieval service tests |
| Collection or document processing | `langconnect/services/` | Collection or processor tests |
| Postgres persistence | `langconnect/database/postgres/` | Matching repository tests |
| Graph behavior | `langconnect/database/neo4j/`, graph service | Graph build/query/lifecycle tests |
| Auth or idempotency | Top-level boundary module | Matching unit tests |

## Documentation routing

Open only a document whose condition matches the change.

| Condition | Document |
|---|---|
| Public endpoint, model, or response changes | `docs/api.md` |
| Storage or layer boundaries change | `docs/architecture.md` |
| Test scope is unclear | `docs/testing.md` |
| Startup, environment, database, or operations change | `docs/runbook.md` |
| Service ownership is unclear | `docs/overview.md` |

## Invariants

- Preserve `api -> services -> database`; do not add controller layers.
- Keep Milvus, Postgres, and Neo4j access under `langconnect/database/`.
- Keep `database/collections.py` as a compatibility re-export.
- Use async I/O, Pydantic models for API schemas, and TypedDicts for internal
  shapes.
- Use Ruff line length 88; linting is strict. Do not add redundant
  `pytest.mark.asyncio` annotations.
- Retrieval contracts crossing into tools-service require the matching
  tools-service index and shared contract.

## Test scope

Use `make test TEST_FILE=<path>` inside the quiet task/spec wrappers. The
default affected area is `tests/unit_tests/`; add graph, integration, or
tools-service tests only when that contract changes. Full `make validate` runs
only through the push wrapper.
