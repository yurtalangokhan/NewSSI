# Agentic AI Platform — AGENTS.md

## Monorepo layout

Active code is in `apps/`. Third-party fork/stub trees such as `supabase/` and
`legacy/` have been removed from this branch; do not reintroduce them.

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
make validate       # lint + typecheck + test
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

## Development environment and startup

Before starting services or changing env/compose files, read
`docs/development-environment.md`. In short:

- `configs/.env` belongs to infrastructure compose only.
- `apps/*/.env` files belong to app runtime and are used by VS Code launch
  configs and app Docker Compose.
- Run `make env-init` to create missing env files and keys.
- Run `make env-check` before starting services or handing off env changes.
- All external app traffic must go through Kong on `localhost:8000`.
- Do not commit real `.env` files; commit env validation logic and docs instead.

## Infrastructure configs

```sh
# Prepare/validate env files
make env-init
make env-check

# Dev application services
docker compose --env-file configs/.env -f configs/docker-compose-dev.yml up -d

# Infrastructure (Postgres, Neo4j, Milvus, Airbyte, Keycloak)
docker compose --env-file configs/.env -f configs/docker-compose-services.yml up -d
```

Infrastructure `.env` is at `configs/.env`; per-service runtime `.env` files
live in each `apps/*/` folder.

### Docker verification rule

When changing Dockerfiles, compose files, Python package layout, import paths, or files copied into images, verify Docker explicitly in addition to `make test`:

```sh
make docker-verify
```

This runs `docker compose config` for dev/prod and builds the Python service images from `configs/docker-compose-dev.yml`. For service-specific Dockerfiles that are not part of `configs/docker-compose-dev.yml`, build them directly or through their local compose file. If source imports use top-level packages like `models`, `schema`, or `agents`, the corresponding Dockerfile must copy those directories into the image.

### Git quality gates

Install repo hooks once per clone:

```sh
make hooks-install
```

The hooks use `scripts/quality/check.sh` and must stay lightweight enough for daily use while still blocking broken code:

- **pre-commit** runs staged-file whitespace checks, shell syntax checks, changed-service `make validate`, and `make docker-config` when Docker/compose/package files changed.
- **pre-push** runs checks for files being pushed and runs `make docker-verify` when Docker, compose, package layout, import-sensitive Python service code, or quality scripts changed.
- Do not bypass hooks with `--no-verify` unless the user explicitly approves it for that one action.
- Before committing or asking the user to commit, run the same checks manually with `make quality-staged` or the relevant service `make validate`. For Docker/config/import-layout changes, also run `make docker-verify`.
- Commit/push only green code. If a quality gate fails because of unrelated existing debt, document the failing command and narrow the hook/script rule instead of weakening checks globally.

### Branch and commit naming

Use the existing branch style: `<type>/<kebab-case-description>`.

Common branch types:

- `feature/` for new product or platform capabilities.
- `fix/` for bug fixes and regressions.
- `hotfix/` for urgent production fixes.
- `chore/` for maintenance, build, dependency, or tooling work.
- `docs/` for documentation, agent instructions, and process contracts.

Examples:

- `feature/builtin-ollama-management`
- `fix/auth-redirect-cookie-flow`
- `chore/makefile-standardization`
- `docs/spec-driven-agent-team`

Use concise imperative commit messages, for example
`docs: add spec-driven agent team workflow`.

### Agent pre-push validation flow

Before telling the user that code is ready to push, the agent must evaluate the
changes through Makefile targets instead of ad hoc commands wherever a Makefile
target exists.

**Use the root Makefile for repository-level gates:**

```sh
make quality-staged   # check changed/staged services before commit
make quality-push     # pre-push equivalent for the current branch
make quality-all      # broader local validation when requested or high risk
make validate-services # run every Python service's validate target
make validate         # full local quality-all + docker-verify
make docker-config    # compose config validation
make docker-verify    # compose config + Python service image builds
```

**Use each service Makefile for service-level gates:**

```sh
make -C apps/agent-service validate
make -C apps/rag-service validate
make -C apps/user-service validate
make -C apps/tools-service validate
```

The agent must choose service Makefile targets from the changed files:

| Changed path | Required validation |
|---|---|
| `apps/agent-service/**` | `make -C apps/agent-service validate` |
| `apps/rag-service/**` | `make -C apps/rag-service validate` |
| `apps/user-service/**` | `make -C apps/user-service validate` |
| `apps/tools-service/**` | `make -C apps/tools-service validate` |
| service typing-heavy changes | covered by that service's `make validate` |
| dependency or lockfile changes | run that service's `make install` or `make dev-install` first, then `make validate` |
| migration/model/repository changes | run service tests and the relevant migration target when applicable |
| Dockerfile/compose/package-layout/import-path changes | run `make docker-verify` from the repo root |
| root `Makefile`, hooks, or `scripts/quality/**` | run `make quality-staged` or `make quality-push` from the repo root |

How the agent should use this flow:

1. Inspect `git status --short` and map changed files to affected services.
2. Prefer the affected service's own Makefile from inside the repo root, e.g. `make -C apps/rag-service validate`.
3. If a service Makefile exposes a more specific target for the task, use it instead of open-coded commands: `make typecheck`, `make test-cov`, `make db-migrate`, `make docker-build`, etc.
4. Use root Makefile targets for cross-service validation and Docker/quality hooks: `make validate-services`, `make quality-staged`, `make quality-push`, `make docker-config`, `make docker-verify`, or `make validate` for the full local gate.
5. Only fall back to direct commands when no Makefile target exists, and explain that in the final response.
6. Do not claim all services are validated unless every affected service Makefile gate was actually run and passed.

For web changes, use the web package scripts because `apps/web` does not expose
a Makefile:

```sh
npm --prefix apps/web run lint
npm --prefix apps/web run types:check
npm --prefix apps/web test
```

Validation expectations:

- After every prompt that changes code, config, tests, Docker, compose, package metadata, or quality scripts, run the narrowest relevant service Makefile gates before the final response.
- Before any push-ready handoff, run `make quality-staged` or the relevant `make -C apps/<service> validate` commands. If Dockerfiles, compose files, import paths, package layout, or image copy rules changed, also run `make docker-verify`.
- If the user asks to check all services, run all service gates plus web lint/typecheck and `make docker-verify`.
- If a command fails, fix root causes when they are in scope. If failures are unrelated existing debt, report the failing command, failure count, and why the code is not fully push-ready yet.
- The final response must explicitly say which skills were used, which Makefile/npm gates passed, which gates failed or were skipped, and whether the code is ready to push.
- Do not push to remote branches unless the user explicitly asks for push in that turn.

### Agent development workflow

Use the project skills deliberately before changing code:

- Start by checking applicable skills; use `systematic-debugging` for bugs/build failures and find the root cause before editing.
- Use `brainstorming` for new behavior or larger refactors, then keep the implementation scoped to the smallest useful change.
- Use `test-driven-development` for bug fixes, behavior changes, and refactors: add or update a failing regression test first when practical, then make it pass.
- Use `fastapi` / `fastapi-expert` for FastAPI, Pydantic, SQLAlchemy async, auth, and API architecture changes.
- Use architecture skills for service/folder restructuring and preserve the repo layering: route -> controller -> service -> repository, with schemas/models kept in their own directories.
- Use `.agents/team.yaml` as the provider-neutral development team contract
  when a task benefits from planner, architect, implementer, tester, reviewer,
  or docs-maintainer roles. Codex, OpenCode, or another agent provider may map
  these roles to native subagents, separate sessions, or sequential execution
  by the main agent.
- At the end of implementation work, report the selected skills and validation results, including typecheck. Say "ready to push" only when the applicable service Makefile `validate` gates, root quality/Docker gates, and web scripts are green for the changed surface.

### Documentation and context reading

Agents must treat repository documentation as shared working memory for
understanding the codebase before making changes.

- Before changing a service, UI area, integration, or flow, scan the relevant
  `docs/**/*.md` files and any related `.tmp/**/*.md` files. Prefer `rg` or
  `find` to discover likely matches by feature name, service name, route, or
  domain concept.
- `docs/` is for durable system knowledge: architecture overviews, service
  boundaries, component and flow explanations, runbooks, and decisions that
  should remain true after the current task is finished.
- `.tmp/` is for active working context: temporary specs, implementation notes,
  instructions, investigation notes, and shared memory that helps agents
  coordinate on the current feature or bugfix.
- If a task introduces or materially changes a component, service boundary,
  API flow, auth flow, integration, data model, or agent behavior, update or
  create the matching documentation as part of the same change. Use `docs/`
  for stable knowledge and `.tmp/` for in-progress specs or instructions.
- Keep docs concise and navigable. A future agent should be able to understand
  what the component or flow does, where the important files are, how data
  moves through it, what invariants matter, and which validation commands prove
  it still works.
- Do not let `.tmp/` become the only source of truth for completed work. When a
  temporary spec captures lasting architecture or flow knowledge, migrate that
  knowledge into `docs/` before calling the work complete.

### Spec-driven implementation workflow

Features and larger changes start with a detailed spec document in `.tmp/`.
This is the bridge between design brainstorming and code implementation.

1. **Spec location:** All active spec documents live in `.tmp/` at the repo
   root. Name pattern: `.tmp/<topic>-design.md`. Start from
   `.agents/templates/spec-template.md` unless an existing spec already covers
   the work.
2. **Spec content:** Must cover architecture, component interfaces, data flow,
   error handling, testing strategy, implementation order, per-file changes,
   validation gates, acceptance criteria, resolved decisions, and agent handoff
   notes.
3. **Before implementing:** An agent must first read the full spec from
   `.tmp/<topic>-design.md` and confirm they understand the design. If the spec
   is unclear or incomplete, report back — do not guess.
4. **Follow the spec order:** Implement steps in the order listed in the spec's
   "Implementation Order" section. Each step corresponds to a concrete set of
   file changes.
5. **Validation gates:** After each spec step, run the relevant service
   `make validate` before moving to the next step. Docker/compose changes
   require `make docker-verify`.
6. **Spec updates:** If implementation reveals design gaps, update the spec
   document first, then continue coding. The spec is the source of truth.
7. **Cleanup:** Once the feature is complete and validated, the spec document
   can be moved to `docs/superpowers/specs/` as a permanent record.

### Spec-driven agent team workflow

The repository defines a small provider-neutral development team in
`.agents/team.yaml`. Use this contract for larger changes, multi-step features,
cross-service work, or any task where shared context and review loops reduce
risk.

**Team files:**

- `.agents/team.yaml` defines roles, workflows, shared context file patterns,
  and provider fallback behavior.
- `.agents/roles/*.md` defines role-specific instructions for planner,
  architect, implementer, tester, reviewer, and docs-maintainer agents.
- `.agents/templates/spec-template.md` is the durable template for new
  `.tmp/<topic>-design.md` specs.

**Provider mapping rules:**

- Codex should use native multi-agent tools when available; otherwise execute
  the same role sequence in the main session.
- OpenCode or other providers should map `.agents/team.yaml` roles to their
  own agent/task runner primitives while preserving the same files and report
  contracts.
- If no subagent mechanism exists, do not invent parallelism. Execute the
  workflow sequentially in the main agent and keep the same `.tmp` artifacts.

**Shared context contract:**

- `.tmp/<topic>-design.md` is the single active source of truth for the task.
- `.tmp/<topic>-task-<n>-brief.md` contains the exact requirements for one
  implementation step.
- `.tmp/<topic>-task-<n>-report.md` contains the implementer's status, changed
  files, validation commands, results, and concerns.
- `.tmp/<topic>-progress.md` records completed steps so future agents can
  resume without rereading conversation history.

**Role flow:**

1. **Planner:** analyzes the request, reads relevant docs, creates or updates
   the `.tmp/<topic>-design.md` shared spec, and defines implementation order.
2. **Architect:** reviews the spec for service boundaries, interfaces, data
   flow, and validation gaps before implementation begins.
3. **Implementer:** works one task brief at a time, follows TDD for behavior
   changes, preserves existing user changes, and writes the task report.
4. **Tester:** confirms regression coverage and maps changed files to required
   Makefile/npm gates.
5. **Reviewer:** checks each task for spec compliance and code quality. Critical
   and Important findings must be fixed and re-reviewed before moving on.
6. **Docs maintainer:** updates durable docs when the completed work changes
   architecture, service boundaries, API flow, auth flow, integration, data
   model, or agent behavior.

**Execution rules:**

- Do not dispatch multiple implementers in parallel against the same working
  tree unless their file ownership is explicitly disjoint in the spec.
- Give each subagent the smallest useful context: its role prompt, the task
  brief, the shared spec sections named in the brief, and relevant files.
- Keep long handoffs in files, not pasted conversation text.
- Update `.tmp/<topic>-progress.md` after each reviewed task completes.
- If implementation reveals a spec gap, update the spec before continuing.
- Final responses must state which roles/skills were used, which validation
  gates passed or failed, and whether the code is ready to push.

### Auth/OIDC redirect and cookie workflow

- Treat login, logout, callback redirect, and browser cookie changes as security-sensitive behavior changes.
- Use TDD for auth behavior: add or update regression tests for redirect URI merging, post-logout redirect handling, Set-Cookie creation/clearing, and open redirect validation before changing production code.
- Do not replace Keycloak client `redirectUris`, `webOrigins`, or `post.logout.redirect.uris` from env/runtime values. Merge existing Keycloak values with new env/runtime values while preserving manual admin entries.
- For browser-accessible origins, ensure runtime callback and post-logout redirect URIs are registered before redirecting the user to Keycloak.
- Validate auth changes through the affected service gates (`make -C apps/user-service validate`, web lint/typecheck/tests when web changes) and live HTTP/cookie checks through Kong when services are running.

Airbyte remains an active datasource integration. The `docker-bin/docker` binary
is mounted into the Airbyte worker by `configs/docker-compose-services.yml`, and
`airbyte-destination-embedding/` contains the custom destination connector source.

## Things to avoid

- Do not re-add the removed `supabase/` third-party source clone or `legacy/` old stack.
- Do not remove `docker-bin/docker` unless Airbyte worker startup is updated to use another Docker CLI source.
- Do not touch `airbyte-destination-embedding/` unless the task explicitly mentions Airbyte destinations.
- `providers/` is empty.
- The web app's `lib/opal/` is excluded from the main `tsconfig.json` (`"exclude": ["lib/opal"]`). Type-check it separately if needed.
- Dont push the commits to remote branch and dont create merge request.
