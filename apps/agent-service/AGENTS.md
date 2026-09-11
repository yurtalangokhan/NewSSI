# Agent service index

Use this file only for work under `apps/agent-service/`. Root `AGENTS.md` owns
the workflow; this file tells you where agent-service code, tests, and durable
documentation live.

## Ownership and source map

Agent service owns chat, streaming, LangGraph orchestration, dynamic agent
definitions, built-in recipes, memory, and the tools-service gateway.

```text
src/api/routes/                 HTTP routes
src/controller/                 Use-case orchestration
src/service/                    Business logic
src/repository/                 Data access
src/schema/                     Request and response schemas
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
| API or schema | `src/api/routes/`, `src/schema/`, then controller | Matching route/controller tests |
| Use case | `src/controller/`, `src/service/` | `tests/controller/`, `tests/service/` |
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

- Keep `route -> controller -> service -> repository` boundaries.
- Keep FastAPI types out of services and concrete I/O out of domain modules.
- Preserve `ToolsServiceToolGateway`; credentials never enter model-visible
  arguments.
- Put generic tools in tools-service, not `src/agents/`.
- Keep recipes in `application/recipes.py` and graph registration in
  `strategies/registry.py`.
- Preserve the compatibility exports in `src/agents/__init__.py` unless the
  task explicitly changes that API.
- Use Ruff line length 100 and `from i18n import t` for user-facing messages.

## Test scope

Use `make test-file FILE=<path>` inside the quiet task/spec wrappers. Default
core tests exclude `tests/app`, `tests/voice`, and `tests/integration`; include
those suites only when their surfaces change. Full `make validate` runs only
through the push wrapper.
