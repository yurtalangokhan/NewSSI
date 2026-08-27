# Agentic AI Platform — AGENTS.md

## Monorepo layout

| directory | language | what |
|---|---|---|
| `apps/web/` | TypeScript (Next.js 16) | Frontend (Onyx) |
| `apps/agent-service/` | Python 3.11+ | LangGraph agents (FastAPI + Streamlit) |
| `apps/rag-service/` | Python 3.11+ | RAG / LangConnect (FastAPI + pgvector + Neo4j) |
| `apps/user-service/` | Python 3.11+ | Auth, users, roles (FastAPI + SQLAlchemy) |
| `apps/tools-service/` | Python 3.11+ | MCP tools (FastMCP) |
| `configs/` | — | Central `.env`, docker-compose (infra + dev + prod) |
| `airbyte-destination-embedding/` | Python | Custom Airbyte destination (do not touch) |

`.github/` is empty — **no CI pipeline**. All validation is local via git hooks + Makefile.

## Documentation reference

| File | What it covers |
|---|---|
| `docs/architecture-overview.md` | C4 diagrams, system context, containers, dev lifecycle, startup |
| `docs/coding-standards.md` | Coding conventions, clean-code practices, code smells, per-service rules |
| `docs/deployment.md` | Docker Compose dev/prod, image build, startup order, health checks |
| `docs/developer-guide.md` | Full repo tree, layer rules, commands, testing, validation, quirk table |
| `docs/env-variables.md` | Consolidated env vars for all services + infrastructure |
| `docs/service-interactions.md` | Request flows, auth chain, service dependency map, integration patterns |
| `docs/code-review-skills.md` | Code review skill recommendations |
| `AGENTS.md § Progress tracking rule` | Mandatory progress.md updates after each task completion |
| `docs/api/agent-service.md` | Agent service endpoints (100+ routes) |
| `docs/api/user-service.md` | User service endpoints (auth, users, roles) |
| `docs/api/rag-service.md` | RAG service endpoints (collections, graph, search) |
| `docs/api/tools-service.md` | Tools service endpoints (MCP tools, 44 tools) |

Load the relevant doc when deep work is needed on that domain.

---

## Python services — common commands

Every Python service uses **uv** + **hatchling**. All have the same Makefile targets:

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

### Service-specific quirks

**agent-service:**
- Default `test` skips `tests/app`, `tests/voice`, `tests/integration`. Use `make test-all` for everything.
- `make run` is alias for `make run-service` (via `src/run_service.py`).
- `make run-streamlit`, `make run-studio` (LangGraph dev).
- Alembic under `src/core/db/migrations/` — `make migrate`, `make new-migration NAME="..."`.
- `make info` lists registered agents.
- Ruff config in `ruff.toml`, not `pyproject.toml`. Line length: 100.
- `FAKE_MODEL` env var enables dev without real LLM API key.

**rag-service (LangConnect):**
- Default `test` runs `IS_TESTING=true uv run pytest tests/unit_tests`. Use `make test TEST_FILE=tests/` to override.
- Line length: **88** (others use 100).
- `make format` runs `ruff format` then `ruff check --fix` (both).
- Ruff select: `["ALL"]` — very strict. Expect many ignores in `pyproject.toml`.

**user-service:**
- Alembic for migrations: `make db-migrate`, `make db-migrate-create`, `make db-migrate-rollback`, `make db-reset`.
- DB containers: `make db-up`, `make db-down`.
- Services return dicts via `_to_dict()` helpers instead of Pydantic serialization.

**tools-service (FastMCP):**
- Entrypoint at `apps/tools-service/server.py` (not in `src/`).
- Default port: `MCP_PORT=8001`; Docker overrides to 8003.

---

## Kong API gateway (port 8000)

All external traffic goes through Kong on port 8000. Service ports are `.env`-configurable — never hardcode them.

| Kong path | upstream | auth |
|---|---|---|
| `/api/auth`, `/health`, `/auth` | user-service / agent-service | public |
| `/api/users/*`, `/api/roles/*`, `/api/permissions/*` | user-service | JWT |
| `/api/agents/*`, `/api/chat/*`, `/api/query/*`, `/auth/*` | agent-service | JWT |
| `/api/rag/*` | rag-service | JWT |
| `/api/mcp` | tools-service | JWT |
| `/internal/{user-service,rag-service,mcp}` | respective service | internal token |

Config at `configs/kong/kong.yml` — template vars resolved from `configs/.env`.

Dev: services run on host, Kong reaches them via `host.docker.internal:PORT`. Docker: by service name.

---

## FastAPI architecture (agent-service, user-service)

```
api/routes/*.py  →  controller/*.py  →  service/*.py  →  repository/*.py
(HTTP handlers)     (orchestration)     (business logic)   (data access)
```

- Routes: parse params, call controller, return response. No business logic.
- Controllers: orchestrate, translate domain errors → HTTP statuses. Stateless singletons.
- Services: pure domain logic. Raise `ValueError`, `NotFoundError` etc. Never HTTP exceptions.
- Repositories: wrap SQLAlchemy async sessions. Use `async with self._session()` (auto-commit).
- Core exceptions in `core/exceptions.py`. Config via `pydantic-settings` with `@lru_cache`.
- Services/controllers use `_instance` + `get_*()` singleton pattern.

**rag-service** has a flatter stack: `langconnect/api/*.py` → `langconnect/services/*.py` → `langconnect/database/*`.
**tools-service** categories extend `BaseToolCategory` ABC in `src/core/`. Registry in `src/core/registry.py`.

---

## Web frontend (Next.js 16)

**Commands:**
```sh
npm run dev            # next dev --webpack (explicit --webpack flag)
npm run build          # next build (output: "standalone")
npm run lint           # eslint src --ext .js,.jsx,.ts,.tsx
npm run types:check    # tsgo --noEmit --project tsconfig.types.json
npm run format         # prettier --write "src/**/*.{ts,tsx,js,jsx,json,css,md}"
npm test               # jest (two projects: unit + integration)
npm run test:ci        # jest --ci --maxWorkers=2 --silent --bail
npm run test:e2e       # playwright (tests/e2e/)
```

**Absolute imports only:** `@/*` → `src/`, `@tests/*` → `tests/`, `@opal/*` → `lib/opal/src/*`, `@opal/types/*` → `lib/opal/src/types/*`.

`lib/opal/` is a npm workspace (`"@onyx/opal"`) and is **excluded** from main `tsconfig.json`. Type-check separately if needed.

### Conventions that differ from defaults

- **Components**: `function Component()`, not arrow functions. **Props** → `interface Props`.
- **No `dark:` Tailwind modifier.** Colors defined in `tailwind-themes/` + `colors.css` handle dark mode. Exception: `createLogoIcon` in `icons/icons.tsx`.
- **Class names**: `cn()` from `@/lib/utils`, never raw strings.
- **Icons**: ONLY from `src/icons/`. Never react-icons, lucide, phosphor-icons directly.
- **Text**: `<Text>` from `@/refresh-components/texts/Text`, never naked `<p>/<h1>`.
- **Form inputs**: Use `@/refresh-components/` or `@opal/` components, never raw `<input>/<textarea>/<button>`.
- **Colors**: Only custom tokens (`bg-background-neutral-03`, `text-02`, `border-01`). No Tailwind built-in colors.
- **Data fetching**: `useSWR` (swr), fetch at component level, not parent.
- **Tests**: Co-located with source. Two Jest projects: unit (node) + integration (jsdom). Use `setupUser()` from `@tests/setup/test-utils`, not raw `userEvent.setup()`.
- `jest.spyOn(global, "fetch")` for mocking HTTP — comment which endpoint each mock serves.
- Playwright e2e in `tests/e2e/`.
- Sentry: conditional — only enabled when `SENTRY_AUTH_TOKEN` + `NEXT_PUBLIC_SENTRY_DSN` are set.
- `next.config.js` has `typedRoutes: true`.

---

## Development lifecycle rules

### 0. Documentation and shared context

Treat repository documentation as shared working memory before changing code.

- Before changing a service, UI area, integration, or flow, scan the relevant
  `docs/**/*.md` files and any related `.tmp/**/*.md` files. Use `rg` to
  discover likely matches by feature name, service name, route, or domain
  concept.
- Use `docs/` for durable system knowledge: architecture overviews, service
  boundaries, component and flow explanations, runbooks, and decisions that
  should remain true after the current task is finished.
- Use `.tmp/` for active working context: temporary specs, implementation
  notes, investigation notes, and shared memory that helps agents coordinate on
  the current feature or bugfix.
- If a task introduces or materially changes a component, service boundary, API
  flow, auth flow, integration, data model, or agent behavior, update or create
  the matching documentation as part of the same change.
- Do not let `.tmp/` become the only source of truth for completed work. Move
  lasting architecture or flow knowledge into `docs/` before calling the work
  complete.

### 1. Before coding

Load the relevant skill first:
- `brainstorming` — new features, refactors, behavior changes
- `systematic-debugging` — bugs or build failures
- `test-driven-development` — bug fixes, behavior changes
- `fastapi` / `fastapi-expert` — FastAPI, Pydantic, SQLAlchemy, auth
- `frontend-design` — UI changes

### Architecture & code-quality rules (SOLID, OOP, clean architecture)

Committed and pushed code must obey the SOLID principles and clean-architecture
rules documented in `docs/oop-solid-architecture.md`. These are enforced by a
**blocking gate** (`scripts/quality/check_architecture.py`, wired into the
commit/push hooks via `scripts/quality/check.sh`). Read that doc before coding
or reviewing.

- Dependency direction points inward: `domain/` must never import
  `integrations`, `core.db`, or concrete `repository` implementations.
- Delivery adapters (`fastapi`, `UploadFile`, `HTTPException`, `status`) stay at
  the API edge — never in `service/` or `domain/`.
- Repositories, clients, and gateways live in their own layers, not in
  `service/` or `controller/`.
- No generic bucket modules (`Utils`, `Helpers`); names must explain ownership.
- The gate checks only the files you changed (pre-existing offenders do not
  block unless you touch them). HARD findings fail the commit/push; size and
  complexity are WARN-only. See `docs/coding-standards.md` for the full rule
  table and how to run the check locally.
- The quality runner also computes a 0-100 score from architecture findings.
  `quality-staged` and `quality-push` fail below `QUALITY_SCORE_MIN`, which
  defaults to `80`. Use `make quality-score` to evaluate the full tracked tree.

### Spec-driven implementation workflow

Features and larger changes start with a detailed spec document in a topic
folder under `.tmp/`. This spec is the bridge between design brainstorming and
code implementation.

1. **Spec location:** Active spec documents live in `.tmp/<topic>/`.
   Name pattern: `.tmp/<topic>/design.md`. Start from
   `.agents/templates/spec-template.md` unless an existing spec already covers
   the work. Keep task briefs and handoff reports inside the same topic folder
   instead of placing them directly under `.tmp/`.
2. **Spec branch:** Each new spec must start on its own local branch before
   the spec is written. Use the existing branch style, for example
   `feature/<topic>` for product changes and `docs/<topic>` for process-only
   specs. If a dirty worktree already exists, create the branch without
   reverting unrelated user changes and document that context in the spec.
3. **Spec content:** Cover architecture, component interfaces, data flow, error
   handling, testing strategy, implementation order, per-file changes,
   validation gates, acceptance criteria, resolved decisions, and agent handoff
   notes.
4. **Before implementing:** Read the full spec and confirm the design is clear.
   If the spec is unclear or incomplete, update it before coding.
5. **Follow the spec order:** Implement steps in the order listed in the
   spec's "Implementation order" section. Each step maps to a concrete set of
   file changes.
6. **Validation gates:** After each spec step, run the relevant service
   `make validate` before moving to the next step. Docker/compose changes
   require `make docker-verify`.
7. **Spec updates:** If implementation reveals design gaps, update the spec
   document first, then continue coding. The spec is the source of truth.
8. **Cleanup:** Once the feature is complete and validated, move durable
   knowledge from the spec into `docs/`.

### Spec-driven agent team workflow

The repository defines a provider-neutral development team in
`.agents/team.yaml`. Use this contract for larger changes, multi-step features,
cross-service work, or tasks where shared context and review loops reduce risk.

**Team files:**

- `.agents/team.yaml` defines roles, workflows, shared context file patterns,
  and provider fallback behavior.
- `.agents/roles/*.md` defines role-specific instructions for planner,
  architect, implementer, tester, reviewer, and docs-maintainer agents.
- `.agents/templates/spec-template.md` is the durable template for new
  `.tmp/<topic>/design.md` specs.

**Provider mapping rules:**

- Codex should use native multi-agent tools when available; otherwise execute
  the same role sequence in the main session.
- OpenCode or other providers should map `.agents/team.yaml` roles to their own
  agent/task runner primitives while preserving the same files and report
  contracts.
- If no subagent mechanism exists, execute the workflow sequentially in the
  main agent and keep the same `.tmp` artifacts.

**Shared context contract:**

- `.tmp/<topic>/design.md` is the single active source of truth for the task.
- `.tmp/<topic>/plan.md` contains the implementation plan when the task needs
  one.
- `.tmp/<topic>/progress.md` records completed steps so future agents can
  resume without rereading conversation history.
- `.tmp/<topic>/tasks/task-<n>-brief.md` contains the exact requirements for
  one implementation step.
- `.tmp/<topic>/tasks/task-<n>-report.md` contains the implementer's status,
  changed files, validation commands, results, and concerns.
- `.tmp/<topic>/tasks/task-<n>-diff.md` contains a task-specific diff package
  when a reviewer needs one.
- `.tmp/<topic>/reviews/task-<n>-review.md` and
  `.tmp/<topic>/reviews/task-<n>-rereview-<m>.md` contain reviewer output.
- `.tmp/<topic>/reviews/architect-review.md` contains architect review output
  when a separate architecture check is used.

**Role flow:**

1. **Planner:** Analyzes the request, reads relevant docs, creates or updates
   the `.tmp/<topic>/design.md` shared spec, and defines implementation order.
2. **Architect:** Reviews the spec for service boundaries, interfaces, data
   flow, and validation gaps before implementation begins.
3. **Implementer:** Works one task brief at a time, follows TDD for behavior
   changes, preserves existing user changes, and writes the task report.
   **Must run the architecture & code-quality gate** (`make quality-staged` or
   `python3 scripts/quality/check_architecture.py --changed`) on the files it
   changed, confirm the quality score meets `QUALITY_SCORE_MIN`, and resolve
   every HARD finding before the task is considered done.
4. **Tester:** Confirms regression coverage and maps changed files to required
   Makefile/npm gates, including the architecture gate.
5. **Reviewer:** Checks each task for spec compliance and code quality.
   **Also checks the architecture gate**: HARD findings on changed files are
   blocking, a score below `QUALITY_SCORE_MIN` is blocking, and both must be
   fixed and re-reviewed before moving on. Critical and important findings must
   be fixed and re-reviewed before moving on.
6. **Docs maintainer:** Updates durable docs when completed work changes
   architecture, service boundaries, API flow, auth flow, integration, data
   model, or agent behavior.

**Execution rules:**

- Do not dispatch multiple implementers in parallel against the same working
  tree unless their file ownership is explicitly disjoint in the spec.
- Give each subagent the smallest useful context: its role prompt, the task
  brief, the shared spec sections named in the brief, and relevant files.
- Keep long handoffs in files, not pasted conversation text.
- Update `.tmp/<topic>/progress.md` after each reviewed task completes.
- If implementation reveals a spec gap, update the spec before continuing.
- **Every task must leave the architecture & code-quality gate green for its
  changed files and meet the quality score threshold.** The implementer runs it
  locally; the reviewer confirms it in the task report. A task that introduces
  a HARD architecture finding or drops below `QUALITY_SCORE_MIN` is not complete
  until the issue is fixed.
- Final responses must state which roles/skills were used, which validation
  gates passed or failed (including the architecture gate), and whether the code
  is ready to push.

### Progress tracking rule

Every spec-driven implementation task MUST update the spec's progress file
immediately after completion. This is a hard gate — no task is considered
done until its progress entry exists.

**What to update:**

- `.tmp/<topic>/progress.md` — the single source of truth for task completion
  status across agent sessions.

**When to update:**

- After the implementer writes the task report AND the reviewer approves it
  (or the main agent validates it when no separate reviewer is used).
- Before starting the next task in the same service or topic.

**Required format in `progress.md`:**

Each completed task must appear in the `## Completed` section with:

```markdown
- Completed <TASK-ID> <short description> and wrote
  `.tmp/<topic>/tasks/task-<TASK-ID>-report.md`.
```

The `## Not started` section must be updated to remove completed tasks.
The `## Next implementation order` section must be updated if the
completion changes the recommended next step.

**Why this matters:**

- Agents resume work across sessions. Without a progress file, the next
  agent must re-read the entire conversation history to know what is done.
- The progress file is the handoff contract between agent roles (implementer
  → reviewer → tester → next implementer).
- It prevents duplicate work and enables parallel task dispatch when write
  sets are disjoint.

** Enforcement:**

- The docs-maintainer role (or main agent) checks `progress.md` completeness
  before declaring a phase done.
- If a task report exists but `progress.md` is not updated, the task is
  NOT considered complete.

### 2. Coding

- Follow the layered architecture: route → controller → service → repository.
- **Read `docs/oop-solid-architecture.md`** (SOLID, OOP fundamentals, clean
  architecture) before writing or reviewing code. Committed/pushed code must
  obey these rules; they are enforced by the architecture gate (see §4).
- Keep one file per domain entity in routes.
- Define domain exceptions in `core/exceptions.py`, not scattered.
- Use async for all DB operations. `asyncio_mode = "auto"` in pytest.
- Web: all imports absolute with `@/` prefix. No relative imports.
- Web: only custom components from `@/refresh-components/` or `@opal/`.
- Web: never raw `<p>`/`<h1>`/`<input>`/`<button>`/`<img>`; use `<Text>` and
  `@/refresh-components`. Never `lucide`/`react-icons`/`phosphor`; use `@/icons`.

### 3. Testing

```sh
# Python service — run affected service's tests
make -C apps/<service> test

# Single file
make -C apps/agent-service test-file FILE=tests/path/to/test.py    # agent-service only
uv run pytest tests/path/to/test.py                                 # other services

# Web
npm --prefix apps/web test -- --testPathPattern="ComponentName"
npm --prefix apps/web test:ci
```

- agent-service default test skips `tests/app`, `tests/voice`, `tests/integration`.
- rag-service default test runs only `tests/unit_tests`.
- Web: tests co-located with source. Two Jest projects (unit + integration).

### 4. Validation — always run before commit/push

**Mandatory architecture & code-quality gate.** Committed and pushed code must
pass `scripts/quality/check_architecture.py`, which enforces the SOLID / clean
architecture rules from `docs/oop-solid-architecture.md`. **Agents must resolve
every HARD finding in the files they change before the code can be committed or
pushed.** The gate runs automatically in the pre-commit and pre-push hooks, but
you must run it locally yourself during development so you are not surprised:

```sh
# Local, on the files you have changed (mirrors the hook):
make quality-staged
# Or run the gate directly on specific files:
QUALITY_FILES="apps/<service>/src/path/to/file.py" \
  python3 scripts/quality/check_architecture.py --changed
QUALITY_FILES="apps/<service>/src/path/to/file.py" \
  python3 scripts/quality/score.py --changed --min-score 80
# Full-tree report (non-blocking, for trend/baseline only):
make architecture-check
make quality-score
```

HARD findings (blocking) cover: HTTP-framework leakage in `service`/`domain`,
repositories/clients/gateways in the wrong layer, `domain`→`core.db`/integration
dependency inversion, generic `Utils`/`Helpers` bucket names, raw HTML/UI
primitives and banned icon imports on the web side. See
`docs/coding-standards.md` ("Architecture & code-quality gate") for the full
rule table. The quality score starts at 100, subtracts 25 points per HARD
finding and 5 points per WARN finding, and fails below `QUALITY_SCORE_MIN`
(default `80`) in staged/push quality gates. **Do not bypass with
`--no-verify`; fix the finding.**

Run the **narrowest** service gate for changed files:

| Changed files | Command |
|---|---|
| `apps/agent-service/**` | `make -C apps/agent-service validate` |
| `apps/rag-service/**` | `make -C apps/rag-service validate` |
| `apps/user-service/**` | `make -C apps/user-service validate` |
| `apps/tools-service/**` | `make -C apps/tools-service validate` |
| `apps/web/**` | `npm --prefix apps/web run lint && npm --prefix apps/web run types:check && npm --prefix apps/web test` |
| dependency/lockfile | run `make install` or `make dev-install` first, then `make validate` |
| Dockerfile/compose/import path | also run `make docker-verify` from repo root |
| root Makefile/hooks/quality scripts | `make quality-staged` or `make quality-push` |

Each service's `make validate` runs: `lint` → `typecheck` → `test`.

The hooks also run the **architecture & code-quality gate**
(`scripts/quality/check_architecture.py`), which blocks commits/pushes that
violate the SOLID / clean-architecture rules in `docs/oop-solid-architecture.md`.

### 5. Git quality gates

```sh
make hooks-install   # install pre-commit + pre-push hooks (one-time per clone)
```

The hooks run `scripts/quality/check.sh`:

- **pre-commit** (`make quality-staged`): whitespace check, shell syntax, changed-service `make validate`, **architecture & code-quality gate**, `make docker-config` for Docker/compose changes.
- **pre-push** (`make quality-push`): same checks against upstream diff range. Also `make docker-verify` for Docker/package-layout changes.

Do not bypass hooks with `--no-verify` unless the user explicitly approves.

**Mandatory before every push:** run `make quality-push` (or `make quality-staged`
locally) and confirm the architecture gate is green for the files you changed.
If the gate reports HARD findings on files in your change, you MUST fix them in
the same commit/branch — the push is blocked until they pass. This is part of
the development lifecycle: architecture quality is not optional and is checked
on every commit and push.

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

### 6. Preparing to push

1. `git status --short` → identify changed services
2. Run each affected service's `make validate` (or web equivalents)
3. **Run `make quality-staged` → confirm the architecture & code-quality gate is green and the quality score meets `QUALITY_SCORE_MIN` for the files you changed. Fix any HARD finding or score regression before proceeding.**
4. If Docker/compose/imports changed: `make docker-verify` (compose config + image build)
5. If root config/hooks changed: `make quality-push`
6. If cross-service impact: `make validate` (quality-all + docker-verify)
7. Only say "ready to push" when all applicable gates are green, **including the architecture gate and quality score threshold**

```sh
# Fast path: validate one service
make -C apps/rag-service validate

# Full gate: all services + Docker
make validate
```

---

## Environment & startup

```sh
make env-init       # create missing .env files and keys
make env-check      # validate env files before starting services
```

- `configs/.env` → third-party services compose only.
- `apps/*/.env` → per-service runtime env (used by VS Code + app Docker Compose).
- Do not commit real `.env` files.

**Start order:**
```sh
# Third-party services, required Ollama models, and app microservices
make stack-up
```

Health checks: `curl http://localhost:8000/health/`, `curl http://localhost:8000/api/health`

## Ollama operations

Use this contract whenever Ollama runtime ownership or model data is in scope.

- Manage Ollama with `make third-party-up` and `make ollama-models`; do not
  run host `ollama serve`.
- Never delete or recreate the external Docker volume named `ollama`, and never
  use volume-removal flags during Ollama work.
- Before a destructive handover, verify the Compose labels, the read-write
  `ollama` mount at `/root/.ollama`, and NVIDIA GPU availability.
- Redis remains required infrastructure and must not be removed as part of
  Ollama work.

## Things to avoid

- Do not re-add `supabase/` or `legacy/` directories.
- Do not remove `docker-bin/docker` (mounted into Airbyte worker).
- Do not touch `airbyte-destination-embedding/` unless the task is about Airbyte destinations.
- Do not touch `providers/` (empty).
- Do not push to remote branches unless the user explicitly asks.
- Do not use `--no-verify` without explicit user approval.
