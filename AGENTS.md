# Agentic AI Platform — AGENTS.md

## Monorepo layout

Active code is in `apps/`. The `supabase/` and `legacy/` trees are third-party forks/stubs — **do not edit**.

| directory | language | what |
|---|---|---|
| `apps/web/` | TypeScript (Next.js 16) | Frontend (Onyx) |
| `apps/agent-service/` | Python 3.11+ | LangGraph agent orchestration (FastAPI + Streamlit) |
| `apps/rag-service/` | Python 3.11+ | RAG API (FastAPI + pgvector) |
| `apps/user-service/` | Python 3.11+ | User management (FastAPI + SQLAlchemy + Alembic) |
| `apps/tools-service/` | Python 3.11+ | MCP tools server (FastMCP) |
| `configs/` | — | Central `.env`, docker-compose for infra & dev |
| `airbyte-destination-embedding/` | Python | Custom Airbyte destination |

## Python services — common commands

Every Python service uses **uv** (not pip) and **hatchling** as build backend. All have a standardized `Makefile` with the same targets:

```sh
make install        # uv sync --frozen
make dev-install    # uv sync --frozen --all-groups
make run            # start dev server
make test           # pytest
make lint           # ruff check
make format         # ruff format
make fix            # ruff check --fix
make typecheck      # mypy src/
make clean          # remove caches
```

### Kong API gateway (port 8000)

**All external traffic goes through Kong on port 8000.** Service ports are `.env`-configurable upstreams — never hardcode them.

| Kong path | upstream service | auth |
|---|---|---|
| `/api/auth`, `/health`, `/auth` | user-service / agent-service | public (no JWT) |
| `/api/users/*`, `/api/roles/*`, `/api/permissions/*` | user-service | JWT |
| `/api/agents/*`, `/api/chat/*`, `/api/query/*`, `/auth/*` | agent-service | JWT |
| `/api/rag/*` | rag-service | JWT |
| `/api/mcp` | tools-service | JWT |
| `/internal/{user-service,rag-service,mcp}` | respective service | internal token (no JWT) |

Config at `configs/kong/kong.yml` — upstream template vars (`__USER_SERVICE_UPSTREAM_URL__` etc.) resolved from `configs/.env`.

**Dev (outside Docker):** services run on host, Kong reaches them via `host.docker.internal:PORT`.
**Docker Compose:** services run in containers, Kong reaches them by service name.

### agent-service specifics

- Defined agents live in `src/agents/`; register new agents in `src/agents/agents.py`.
- Default `test` target **skips** `tests/app`, `tests/voice`, `tests/integration`.
- `make test-all` syncs all groups and runs everything.
- `make test-cov` runs tests with coverage (terminal + HTML).
- `make run` is an alias for `make run-service` which uses `src/run_service.py` (loads settings first).
- `make run-streamlit` launches the Streamlit UI (`src/streamlit_app.py`).
- `make run-studio` launches LangGraph Studio (`langgraph dev`).
- `make fix` runs `ruff check --fix`.
- `make format` runs `ruff format`.
- Docker targets: `make docker-up`, `make docker-build`, `make docker-down`, `make docker-logs`.
- Has its own Alembic migrations under `src/core/db/migrations/` — `make migrate`, `make new-migration`, `make migration-status`.
- `make info` lists registered agents.
- `FAKE_MODEL` env var enables development without a real LLM API key.
- Uses pre-commit (`make precommit-install` + `make precommit-run`).

### rag-service specifics

- `make test` runs `IS_TESTING=true uv run pytest tests/unit_tests` (env var set in Makefile).
- `make format` runs `ruff format` (use `make fix` for auto-fix lint).
- `make up-dev` starts Docker services with live reload.

### user-service specifics

- Makefile targets: `db-up`, `db-down`, `db-migrate`, `db-migrate-create`, `db-migrate-rollback`, `db-reset`.
- Uses Alembic for migrations.
- Additional Makefile targets: `test-coverage`, `typecheck`.

### tools-service (FastMCP) specifics

- Entrypoint at repo root: `python server.py` (not in `src/`).
- Default port: 8001 (`MCP_PORT` env); Docker overrides to 8003.

## Code architecture & clean code standards

Every microservice follows the same layered architecture. Understand these layers before making changes:

### FastAPI service architecture (user-service, agent-service)

```
api/routes/*.py     →  controller/*.py     →  service/*.py     →  repository/*.py
(thin HTTP handlers)   (orchestration)         (business logic)     (data access)
```

**Layer rules (enforced by convention):**
- **Routes** (`api/routes/`): Only parse HTTP params, call controller, return response. No business logic. One file per domain entity.
- **Controllers** (`controller/`): Orchestrate service calls, translate domain errors to HTTP statuses via `BaseController._raise_*()` helpers. Hold no state — injected singletons.
- **Services** (`service/`): Pure domain logic. Coordinate multiple repositories and external services. Raise domain errors (e.g. `ValueError`), never HTTP exceptions.
- **Repositories** (`repository/`): Wrap SQLAlchemy async sessions. Each entity has its own repo inheriting `BaseRepository`. Session lifecycle managed in `_session()` context manager (auto-commit/rollback).
- **Schemas** (`schema/`): Pydantic request/response models. Currently underused in user-service (services return raw dicts via `_to_dict()` helpers); prefer Pydantic models for new endpoints.
- **Core** (`core/`): Config (`pydantic-settings`), database engine, domain exceptions (`NotFoundError`, `ConflictError`, etc.), security utilities.

**Key conventions:**
- Services and controllers are singletons: `_instance` module var + `get_*()` function pattern.
- Config loaded via `pydantic-settings` `BaseSettings` with `.env`, cached with `@lru_cache`.
- Domain exceptions defined in `core/exceptions.py` — not scattered across modules.
- Repos use `async with self._session()` for automatic commit/rollback.
- Routes define auth dependencies at router level (`dependencies=[Depends(...)]`) or per-route.

### tools-service (FastMCP) architecture

```
src/core/base.py         →  src/tools/*.py
(BaseToolCategory ABC)      (concrete tool categories)
```

Each tool category extends `BaseToolCategory` ABC, implements `name`, `description`, `label` properties, and `register_tools(mcp)` method. The registry (`src/core/registry.py`) discovers and registers all categories.

### rag-service (LangConnect) architecture

```
langconnect/api/*.py     →  langconnect/services/*.py     →  langconnect/database/*
(routers)                    (business logic)                  (data)
```

Simpler layer stack. Services use raw SQLAlchemy or LangChain primitives directly rather than a repository layer.

### SOLID principles observed in codebase

| Principle | How it's followed |
|---|---|
| **O**pen/Closed | New tool categories extend `BaseToolCategory` without modifying registry. New agents register in `agents/agents.py` dict. New routes add new router files without editing `app.py`. |

### General Python service patterns

- **Config**: `pydantic-settings` `BaseSettings` with `.env` support. Single `Settings` class with computed properties for derived values (e.g. `database_url`).
- **Logging**: `logging.getLogger(__name__)` at module level. agent-service wraps in `get_logger()` helper.
- **Error handling**: Domain exceptions in `core/exceptions.py`. Controllers catch domain errors and convert to `HTTPException`. Services never raise HTTP exceptions.
- **Dependency injection**: Constructor injection for services/repos. Singleton via `get_*()` module-level function with `_instance` global.
- **Async**: All DB operations are async (SQLAlchemy async, asyncpg). Routes use `async def`. `asyncio_mode = "auto"` in pytest config.
- **Type hints**: Full type annotations expected. `mypy` enforces via `make typecheck`. agent-service uses `type: ignore[import-untyped]` for untyped deps.

### Conventions that differ from defaults

- All Python services use `ruff` for lint + format, **not** black/isort/flake8 combo.
- Line length: 100 (user-service, agent-service), 88 (rag-service). Check `pyproject.toml` per service.
- agent-service uses `ruff.toml` (separate file), not `pyproject.toml` for ruff config.
- user-service exports model-to-dict conversions via private `_to_dict()` or `_user_to_dict()` on services — not via Pydantic serialization.
- Repos use `async with self._session()` context manager pattern (auto-commit), not an external UoW.

### Web frontend standards (from `STANDARDS.md` + codebase)

- **Absolute imports**: Always `@/` prefix, never relative.
- **Path aliases**: `@/*` → `src/`, `@tests/*` → `tests/`, `@opal/*` → `lib/opal/src/*`, `@opal/types/*` → `lib/opal/src/types/*`.
- **Components**: Prefer `function Component()`, not arrow functions.
- **Props**: Extract into named interface (`interface Props`).
- **Dark mode**: NEVER use `dark:` Tailwind modifier (colors defined in `colors.css` handle it automatically). Exception: `createLogoIcon` helper in `icons/icons.tsx`.
- **Class names**: Use `cn()` utility from `@/lib/utils`, not raw string interpolation.
- **Icons**: ONLY from `src/icons/` directory. Never from `react-icons`, `lucide`, etc.
- **Text**: Use `<Text>` component from `@/refresh-components/texts/Text`, never raw `<p>`, `<h1>`, etc.
- **Form inputs**: Use components from `@/refresh-components/` or `@opal/`. Never raw HTML `<input>`, `<textarea>`, `<button>`.
- **Colors**: Only custom color tokens (e.g. `bg-background-neutral-03`, `text-02`, `border-01`). Never Tailwind built-in colors.
- **Data fetching**: Prefer `useSWR` from `swr`. Fetch at component level, not parent.
- **Local lib**: `@onyx/opal` (`lib/opal/`) for shared components, layouts, core, icons. Import via sub-path: `@onyx/opal/components`.
- **Tests**: Co-located with source. Use Jest (not Vitest). Two projects: unit (node) + integration (jsdom). Always use `setupUser()` from `@tests/setup/test-utils`.

## Web (Next.js 16)

```sh
npm run dev            # next dev --webpack (note: explicit --webpack flag)
npm run dev:profile    # dev with NEXT_PUBLIC_ENABLE_STATS=true
npm run build
npm run lint           # eslint src/
npm run lint:unused    # eslint with unused-imports rule
npm run types:check    # tsgo --noEmit --project tsconfig.types.json
npm run format         # prettier --write "src/**/*.{ts,tsx,js,jsx,json,css,md}"
npm run format:check   # prettier --check
npm test               # jest (two projects: unit + integration)
npm run test:ci        # jest --ci --maxWorkers=2 --silent --bail
npm run test:coverage  # jest --coverage
npm run test:watch
```

### Testing conventions (web)

- Jest with `ts-jest` (`isolatedModules: true`, no type-checking in tests).
- Two Jest projects: **unit** (node env) and **integration** (jsdom env).
- Tests are **co-located** with source files.
- Always use `setupUser()` from `@tests/setup/test-utils` (not raw `userEvent.setup()`) to get automatic `act()` wrapping.
- Mock `global.fetch` via `jest.spyOn()`, comment which endpoint each mock serves.
- ESM transforms for node_modules configured in `jest.config.js` → `transformIgnorePatterns`.
- Playwright is also available (`@playwright/test`), tests live in `tests/e2e/`.

### Web feature flags (set via env)

- `NEXT_PUBLIC_CLOUD_ENABLED=false`
- `NEXT_PUBLIC_ENABLE_PAID_EE_FEATURES=false`
- `NEXT_PUBLIC_TEST_ENV=false`
- `EE_ENABLED=false`
- `SHOW_EXTRA_CONNECTORS=false`
- `AUTH_TYPE=oidc` (Keycloak)

## Infrastructure configs

```sh
# Dev application services
docker compose -f configs/docker-compose-dev.yml up -d

# Infrastructure (Postgres, Neo4j, Milvus, Airbyte, Keycloak)
docker compose -f configs/docker-compose-services.yml up -d
```

Central `.env` is at `configs/.env` — references the real network addresses. Per-service `.env` files live in each `apps/*/` folder.

## Things to avoid

- **Do not touch** `supabase/` (third-party source clones) or `legacy/` (old stack).
- **Do not touch** `airbyte-destination-embedding/` unless the task explicitly mentions Airbyte destinations.
- The old `AGENTS.md` at `legacy/open-agent-platform/AGENTS.md` documents a completely different codebase (Turbo/Yarn/Next 15) — ignore it.
- `providers/` is empty.
- The web app's `lib/opal/` is excluded from the main `tsconfig.json` (`"exclude": ["lib/opal"]`). Type-check it separately if needed.
- No CI/CD workflows exist (`.github/` directory is absent).
- **Do not push** to remote or dev branches. All work stays local until explicitly told otherwise.