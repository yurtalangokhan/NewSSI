# Agent service index

Use this file only for work under `apps/agent-service/`. Root `AGENTS.md` owns
the workflow; this file tells you where agent-service code, tests, and durable
documentation live.

## Ownership and source map

Agent service owns chat, streaming, LangGraph orchestration, dynamic agent
definitions, built-in recipes, memory, and the tools-service gateway.

```text
src/api/routes/                 HTTP routes
src/api/helpers/                HTTP route pure helpers
src/service/                    Business logic and framework-free use cases
src/service/stream/             Streaming pipeline and timeline tracking
src/service/chat_runs/          Resumable chat-run domain, supervisor, reader, and reaper
src/repository/                 Data access
src/schemas/                    Request and response schemas (Pydantic DTOs)
src/domain/                     Domain types
src/agent_composition/domain/   Ports and definitions
src/agent_composition/application/ Factory, composer, and recipes
src/agent_composition/adapters/ Tools-service adapters
src/agent_composition/runtime/  Agent lifecycle, memory, and safety
src/agents/graphs/strategies/   LangGraph topologies and registry
src/core/db/migrations/         Alembic migrations
src/core/providers/             LLM provider resolution
src/integrations/               External clients
src/memory/                     Memory and context
src/voice/                      Voice surface
tests/                          Tests matching the domains above
```

## Task routing

Use the narrowest row that matches the task.

| Change | Start in | Direct tests |
|---|---|---|
| API or schema | `src/api/routes/`, `src/schemas/`, then the service | Matching route/service tests |
| Use case | `src/service/` (`*_application_service.py`) | `tests/service/` |
| Agent definition or composition | `src/agent_composition/` | `tests/agent_composition/` |
| Graph strategy | `src/agents/graphs/strategies/` | `tests/agents/graphs/` |
| Persistence or migration | `src/repository/`, `src/core/db/` | Matching repository and migration tests |
| Tool integration | `src/agent_composition/adapters/` | Gateway and selector tests |
| Memory or voice | `src/memory/`, `src/voice/` | Matching memory or voice suite |

## Documentation routing

Open only a document whose condition matches the change.

| Condition | Document |
|---|---|
| Public endpoint or schema changes | `docs/api.md` |
| Layer, runtime, or dependency boundary changes | `docs/architecture.md` |
| Composition contracts change | `docs/agent-composition.md` |
| Test scope or suite selection is unclear | `docs/testing.md` |
| Startup, environment, or operations change | `docs/runbook.md` |
| File credentials change | `docs/file-based-credentials.md` |
| Ollama or Google model behavior changes | `docs/ollama.md`, `docs/google-models.md` |
| Service ownership is unclear | `docs/overview.md` |

## Invariants

- Keep `route -> service -> repository` boundaries. Routes own transport and
  the response envelope; `*_application_service` modules orchestrate use cases
  and raise typed `ApplicationError`s. There is no controller layer and no
  `src/controller/` path.
- Keep request and response DTOs in `src/schemas/` (for example
  `schemas/chat.py`, `schemas/chat_runs.py`). The old `src/models/` path no
  longer exists.
- Every outbound HTTP call goes through `core/http/outbound.py` — never
  `httpx.AsyncClient(...)` per request. One pooled client per dependency name,
  and that name must exist under `dependencies:` in `configs/resilience.yaml`.
  Pass timeouts per request; the shared client is process-wide and is closed by
  `security.close_all()` in the lifespan shutdown.
- Do not hand a raw `asyncpg.connect` to a request path: acquire from a pool and
  release it.
- Datasource syncs run in-process through `packages/connector-py`
  (`service/ingest/connector_runtime.py`). Connector configurations are never
  stored in this service: keep only `config_id`/`owner_user_id` and read the
  configuration from user-service when a sync or a live tool needs it.
- Repository sessions are split by intent. SELECT-only methods use
  `self._read_session()` (AUTOCOMMIT: no BEGIN/COMMIT round trip); anything that
  writes uses `self._session()` (one transaction, commit on success).
  `tests/core/test_repository_read_session.py` enforces both directions.
- Blocking callers use `outbound.get_sync_client(dependency)` rather than
  module-level `httpx.get`/`httpx.post`, which build and discard a client — and a
  connection pool — per call.
- Keep FastAPI types out of services and concrete I/O out of domain modules.
- Preserve `ToolsServiceToolGateway`; credentials never enter model-visible
  arguments.
- Put generic tools in tools-service, not `src/agents/`.
- Keep recipes in `application/recipes.py` and graph registration in
  `strategies/registry.py`.
- Preserve the compatibility exports in `src/agents/__init__.py` unless the
  task explicitly changes that API.
- Use Ruff line length 100 and `from localization import t` for user-facing messages.
- Read configuration only through config_manager's typed accessor
  (`from config_manager import env`); direct `os.environ`/`os.getenv` reads are
  not allowed in application code (migrations and bootstrap excepted).

## Test scope

Use `make test-file FILE=<path>` inside the quiet task/spec wrappers. Default
core tests exclude `tests/integration`; include that suite only when its
surface changes. Full `make validate` runs only through the push wrapper.
