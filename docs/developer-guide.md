# Developer Guide

## Repository structure

```
agenticai/
├── apps/                           # All application microservices
│   ├── agent-service/              # LangGraph agent orchestration
│   │   ├── src/
│   │   │   ├── api/routes/         # FastAPI route handlers
│   │   │   ├── controller/        # Orchestration layer
│   │   │   ├── service/           # Business logic
│   │   │   ├── repository/        # Data access (SQLAlchemy async)
│   │   │   ├── schema/            # Pydantic models
│   │   │   ├── core/              # Config, exceptions, DB engine
│   │   │   ├── agents/            # LangGraph agent definitions
│   │   │   └── app.py             # FastAPI app factory
│   │   ├── tests/
│   │   └── pyproject.toml
│   │
│   ├── user-service/               # Auth, users, roles
│   │   ├── src/
│   │   │   ├── api/               # Route files
│   │   │   ├── controller/        # Orchestration
│   │   │   ├── service/           # Business logic (Keycloak integration)
│   │   │   ├── repository/        # SQLAlchemy async repos
│   │   │   ├── schema/            # Pydantic models
│   │   │   ├── core/              # Config, DB, exceptions
│   │   │   └── main.py            # FastAPI app entrypoint
│   │   ├── tests/
│   │   └── pyproject.toml
│   │
│   ├── rag-service/                # RAG / LangConnect
│   │   ├── langconnect/
│   │   │   ├── api/               # FastAPI routers
│   │   │   ├── services/          # Business logic
│   │   │   ├── database/          # PG + Neo4j + Milvus access
│   │   │   ├── models/            # Pydantic models
│   │   │   └── server.py          # FastAPI app entrypoint
│   │   ├── tests/
│   │   └── pyproject.toml
│   │
│   ├── tools-service/              # MCP tools server
│   │   ├── server.py              # FastMCP entrypoint
│   │   ├── src/
│   │   │   ├── core/              # BaseToolCategory, Registry, Auth
│   │   │   ├── tools/             # 14 tool category plugins
│   │   │   └── models/            # Permission catalog
│   │   └── pyproject.toml
│   │
│   └── web/                        # Next.js 16 frontend
│       ├── src/
│       │   ├── app/               # App Router pages
│       │   ├── components/        # Shared components
│       │   ├── refresh-components/ # Onyx design system components
│       │   ├── icons/             # ONLY icon source (never external libs)
│       │   ├── hooks/             # One hook per file
│       │   ├── lib/               # Utilities (cn, etc.)
│       │   ├── providers/         # React context providers
│       │   └── layouts/           # Layout components
│       ├── lib/opal/              # @onyx/opal workspace (shared components lib)
│       ├── tests/
│       └── tailwind-themes/       # Custom color tokens (no Tailwind defaults)
│
├── configs/                        # Centralized config
│   ├── .env                       # Infrastructure env vars
│   ├── docker-compose-services.yml # Infra (PG, Neo4j, Milvus, Airbyte, Keycloak)
│   ├── docker-compose-dev.yml     # App service containers
│   ├── docker-compose-prod.yml    # Production compose
│   └── kong/kong.yml              # Kong API gateway config
│
├── scripts/                        # Dev tooling
│   ├── quality/check.sh           # Pre-commit / pre-push quality gate runner
│   ├── git-hooks/                 # pre-commit, pre-push scripts
│   ├── env_manager.py             # Env file management
│   └── install-git-hooks.sh       # Hook installation
│
├── docs/                           # Documentation
│   ├── api/                       # API endpoint docs per service
│   ├── architecture-overview.md   # System diagrams (Mermaid)
│   └── development-environment.md # Env setup and startup
│
├── Makefile                        # Root Makefile (quality gates, docker-verify, env)
├── AGENTS.md                       # Agent instruction file
└── SKILL.md                        # OpenCode skills configuration
```

---

## Architecture layers

### Python services (agent-service, user-service)

```
api/routes/*.py  →  controller/*.py  →  service/*.py  →  repository/*.py
(HTTP handlers)     (orchestration)     (business logic)   (data access)
```

**Rules:**
- **Routes**: Parse HTTP params, call controller, return response. No business logic. One file per domain entity.
- **Controllers**: Stateless singletons. Orchestrate services, translate domain errors → HTTP statuses.
- **Services**: Pure domain logic. Raise `ValueError`, `NotFoundError` etc. Never HTTP exceptions.
- **Repositories**: Wrap SQLAlchemy async sessions. Auto-commit on context manager exit.
- **Core exceptions**: All domain exceptions live in `core/exceptions.py`.

**Singleton pattern:**
```python
class MyService:
    _instance = None

def get_my_service() -> MyService:
    if MyService._instance is None:
        MyService._instance = MyService()
    return MyService._instance
```

**Config pattern:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_config = {"env_file": ".env"}
    ...

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### rag-service

```
langconnect/api/*.py  →  langconnect/services/*.py  →  langconnect/database/*
(routers)                (business logic)               (PG + Neo4j + Milvus)
```

Flatter stack. Services use raw SQLAlchemy or LangChain primitives directly.

### tools-service

```
src/core/base.py (BaseToolCategory ABC)  →  src/tools/*_tools.py (concrete categories)
src/core/registry.py (discovery + registration)  →  server.py (FastMCP entrypoint)
```

Each tool category extends `BaseToolCategory` and auto-registers on startup. The MCP protocol is served over HTTP at `/mcp`.

---

## API gateway routing

All external traffic goes through **Kong on port 8000**. New callers must use
service-scoped paths. Legacy `/api/*` paths remain as compatibility aliases
while clients migrate.

| Path | Backend service | Auth |
|------|----------------|------|
| `/user-service/health` | user-service | Public |
| `/agent-service/health` | agent-service | Public |
| `/rag-service/health` | rag-service | Public |
| `/tools-service/health` | tools-service | Public |
| `/user-service/api/v1/auth/type`, `/user-service/api/v1/auth/login`, `/user-service/api/v1/auth/refresh` | user-service | Public |
| `/agent-service/api/v1/auth/health` | agent-service | Public |
| `/rag-service/api/v1/graph/health` | rag-service | Public |
| `/user-service/api/v1/*` | user-service | JWT |
| `/agent-service/api/v1/*` | agent-service | JWT |
| `/rag-service/api/v1/*` | rag-service | JWT |
| `/tools-service/mcp` | tools-service | JWT |
| `/internal/{user-service,rag-service,tools-service}/*` | respective service | Internal token |
| `/internal/mcp` | tools-service | Internal token, legacy alias |

---

## API versioning

Backend services use path-based API versioning. The canonical public prefix is
`/api/v1`, and service-scoped Kong routes expose that prefix under each service
path, such as `/agent-service/api/v1/*`.

The shared versioning contract lives in `configs/api-versioning.toml`. Python
services read that file through local `api_versioning` helpers because the repo
doesn't yet have a shared Python package. If the file isn't present in a runtime
image, helpers fall back to the current contract: `/api/v1`.

Use these rules when changing API versions:

- Keep route modules version-neutral. Add prefixes only in app entrypoints and
  service clients.
- Use the local helper's `API_PREFIX` for FastAPI route registration,
  idempotency exclusions, and service-owned routes.
- Use `USER_SERVICE_API_PREFIX` for internal calls to user-service.
- Treat `supported_versions` and `deprecated_versions` as metadata. Updating
  TOML alone must not publish a new route surface.
- To publish `/api/v2`, add explicit v2 router registration or a v2
  sub-application, keep `/api/v1` registered for compatibility, and update Kong,
  frontend clients, API docs, and regression tests in the same change.
- Put breaking request or response schema changes in the versioned API layer.
  Share controller, service, and repository logic when behavior is compatible.

---

## Common development commands

### Python services (every service)

```sh
make install          # uv sync --frozen
make dev-install      # uv sync --frozen --all-groups
make run              # start dev server
make test             # pytest
make test-file FILE=tests/path.py  # single test (agent-service only - others use uv run pytest)
make lint             # ruff check
make format           # ruff format
make typecheck        # mypy src/
make validate         # lint + typecheck + test
```

### Web frontend

```sh
npm run dev           # next dev --webpack
npm run build         # next build (output: "standalone")
npm run lint          # eslint
npm run types:check   # tsgo --noEmit
npm run format        # prettier
npm test              # jest (unit + integration)
npm run test:e2e      # playwright (tests/e2e/)
npm run test:ci       # jest --ci --maxWorkers=2 --silent --bail
```

### Root level

```sh
make env-init         # create missing .env files
make env-check        # validate env files
make docker-config    # validate compose files
make docker-verify    # compose config + image builds
make quality-staged   # pre-commit checks
make quality-push     # pre-push checks
make validate         # all services + docker-verify
```

---

## Working with the code

### Adding a new API endpoint

1. Create the route file (or add to existing) in `api/routes/`
2. Create the controller method in `controller/`
3. Create the service method in `service/`
4. If data access needed: add to repository or create a new one
5. Define request/response models in `schema/`
6. Register the router in `app.py` (or `main.py`)

### Adding a new agent (agent-service)

1. Create agent file in `src/agents/`
2. Register in `src/agents/agents.py`
3. Verify with `make -C apps/agent-service info`

### Adding a new tool (tools-service)

1. Create `src/tools/<name>_tools.py` extending `BaseToolCategory`
2. Implement `name`, `description`, `label`, `register_tools(mcp)`
3. Auto-discovered on next startup

### Adding a frontend feature (web)

1. Use `@/` absolute imports only
2. Components: `function Component()`, props → `interface Props`
3. Use `cn()` from `@/lib/utils` for class names
4. Use `<Text>` for text, icons from `src/icons/` only
5. Use components from `@/refresh-components/` or `@opal/`
6. Fetch data with `useSWR` at component level

---

## Testing patterns

### Python (pytest)

- `asyncio_mode = "auto"` — test functions are `async def`
- Mock HTTP via `httpx` or `responses`
- Agent-service: default test skips `tests/app`, `tests/voice`, `tests/integration`
- Rag-service: default test runs only `tests/unit_tests`

### Web (Jest)

- Co-located tests alongside source files
- Two projects: **unit** (node env) and **integration** (jsdom)
- Use `setupUser()` from `@tests/setup/test-utils`, not raw `userEvent.setup()`
- Mock HTTP: `jest.spyOn(global, "fetch")` — comment which endpoint
- Playwright e2e: `tests/e2e/`

---

## Validation gates

Before committing:
```sh
make quality-staged   # whitespace, shell syntax, changed-service validate, docker-config
```

Before pushing:
```sh
make quality-push     # same as staged against upstream diff, plus docker-verify
```

Fast path per service:
```sh
make -C apps/agent-service validate
make -C apps/rag-service validate
make -C apps/user-service validate
make -C apps/tools-service validate
```

Web:
```sh
npm --prefix apps/web run lint && npm --prefix apps/web run types:check && npm --prefix apps/web test
```

---

## Environment & startup

```sh
make env-init         # create .env files
make env-check        # validate them
```

**Full Docker stack**:
```sh
make stack-up
```

`make stack-up` starts the third-party services from
`configs/docker-compose-services.yml`, pulls the configured Ollama models, and
then starts the application microservices from `configs/docker-compose-prod.yml`.

**Layered startup**:
```sh
make third-party-up
make ollama-models
make prod-up
```

**Health checks:**
```sh
curl http://localhost:8000/user-service/health
curl http://localhost:8000/agent-service/health
curl http://localhost:8000/rag-service/health
curl http://localhost:8000/tools-service/health
```

---

## Per-service quirks

| Service | Line length | Ruff config | Test default | Run command |
|---------|-------------|-------------|--------------|-------------|
| agent-service | 100 | `ruff.toml` | skips app/voice/integration | `uv run src/run_service.py` |
| user-service | 100 | `pyproject.toml` | all tests | `uv run uvicorn src.main:app` |
| rag-service | 88 | `pyproject.toml` (select=ALL) | `tests/unit_tests` only | `uv run uvicorn langconnect.server:APP` |
| tools-service | 100 | `pyproject.toml` | all tests | `uv run python server.py` |

---

## Frontend conventions

| Convention | Rule |
|---|---|
| Imports | Always `@/` prefix, never relative |
| Components | `function Component()` not arrow functions |
| Props | `interface Props`, extracted |
| Dark mode | No `dark:` modifier — handled by `colors.css` |
| Class names | `cn()` from `@/lib/utils` |
| Icons | Only `src/icons/` — never lucide, react-icons, phosphor |
| Text | `<Text>` from `@/refresh-components/texts/Text` |
| Form inputs | `@/refresh-components/` or `@opal/` — never raw HTML |
| Colors | Custom tokens only (`bg-background-neutral-03`, `text-02`, `border-01`) |
| Data fetching | `useSWR` at component level |
| Absolute imports | `@/*` → `src/`, `@tests/*` → `tests/`, `@opal/*` → `lib/opal/src/*` |

---

## Git workflow

1. `git status --short` — identify changed files and affected services
2. Run affected `make validate` commands
3. If Docker/imports changed: `make docker-verify`
4. `git add` files
5. `make quality-staged` — pre-commit gate
6. `git commit` (hooks run automatically)
7. `make quality-push` — pre-push gate
8. `git push` (never `--no-verify` without explicit approval)
