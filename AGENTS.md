# Agentic AI Platform

## Purpose

Produce correct code with minimal context. Stay inside the requested scope,
preserve behavior unless the task changes it, and prefer existing patterns.

## Repository routing

Identify the affected service before reading source or documentation.

```text
apps/web/                         Next.js frontend
apps/agent-service/               FastAPI and LangGraph agents
apps/rag-service/                 FastAPI, pgvector, and Neo4j RAG
apps/user-service/                FastAPI, SQLAlchemy, auth, and users
apps/tools-service/               FastMCP tools
configs/                          Compose and shared infrastructure
airbyte-destination-embedding/    Custom Airbyte destination
```

After selecting a service, use its nearest `AGENTS.md` as the authoritative
code, test, and documentation index. If it is already in context, do not open it
again. Do not read another service index unless the task crosses that boundary.
For cross-service work, load only the affected indexes and shared contract.

All external traffic passes through Kong on port `8000`. Read service ports
from environment configuration; never hardcode them.

## Context discipline

Load information only when it changes the active task.

- Never scan the repository, `docs/`, or `.tmp/` on startup.
- Use the service index before `rg`; use `rg` or symbol references before
  opening a source file.
- Treat documentation tables as routing metadata. Open a document only when
  its stated condition matches the active change.
- Inspect interfaces, schemas, DTOs, and signatures before implementations.
- Default to the active task, its target files, direct dependencies, and direct
  tests. Expand only when correctness requires it.
- Keep tool output bounded. Never load raw validation, test, build, or Docker
  logs when a quiet wrapper covers the command.
- Preserve unrelated user changes and ignore unrelated warnings or debt.

Use global documents only for these conditions:

| Condition | Document |
|---|---|
| Service ownership or system boundary changes | `docs/architecture-overview.md` |
| Cross-service contracts change | `docs/service-interactions.md` |
| Architecture or quality policy is unclear | `docs/oop-solid-architecture.md`, `docs/coding-standards.md` |
| Development setup or commands change | `docs/developer-guide.md` |
| Compose, deployment, or health checks change | `docs/deployment.md` |
| Environment contracts change | `docs/env-variables.md` |

## Spec-driven workflow

Use this workflow for every feature, bugfix, and refactor. Read-only answers,
diagnosis, reviews, and status reports need no spec unless requested.

### Phase 1: Specify

Create a concise topic workspace:

```text
.tmp/<topic>/design.md
.tmp/<topic>/tasks.md
.tmp/<topic>/progress.md    # only when blocked
```

Record scope, decisions, interfaces, tests, and acceptance criteria in
`design.md`. Track atomic tasks as `[ ]` pending, `[/]` active, and `[x]`
verified. A feature spec records contracts and behavior; a bugfix adds a
two-line maximum root cause and reproducing test; a refactor adds an old/new
path and affected-interface map. Do not edit application code in this phase.

### Phase 2: Execute atomic tasks

Resume `[/]` first; otherwise mark the first `[ ]` task active. For only that
task:

1. Write the smallest test that fails for the expected reason.
2. Implement the minimum passing change.
3. Refactor touched code while keeping the focused test green.
4. Run only changed-behavior tests through `validate-task.sh`.
5. Mark `[x]` only after those tests pass.

At task completion, retain only durable decisions, changed contracts, file
paths, and the pass result in the topic files. Stop carrying implementation
details into the next task. Start the next task from `tasks.md`, its task text,
the relevant service index, and its new targets. Context cannot be physically
erased, but stale task material must not be reread or used.

### Phase 3: Validate by lifecycle

Use only quiet wrappers for covered operations.

```sh
# After each task: only tests for its changed behavior
scripts/validate-task.sh --service=<service|root> -- <focused-test-command>

# After every task in the spec is [x]: all tests for changed areas
scripts/validate-spec.sh --service=<service|root> -- <affected-tests-command>

# When the user requests commit preparation: changed-file quality gate
scripts/validate-commit.sh

# Only during push preparation: full affected-service validate
scripts/validate-push.sh --service=<service>

# Root infrastructure or repository-wide push hook
scripts/validate-push.sh
```

Success prints one `[PASS]` line. Failure prints `[FAIL]` plus at most 15
diagnostic lines. Do not read `.tmp/validation/` unless the summary cannot
identify the error; then extract only the relevant block. Fix the reported
issue and retry the same tier. After the same error survives three attempts,
write a three-line maximum blocker to `progress.md`, stop, and notify the user.

Full service `make validate` belongs only to the push tier. Spec completion runs
the complete affected test set, not unrelated service tests or full validation.

## Architecture and quality

Follow the affected service index. The default backend dependency direction is:

```text
route -> controller -> service -> repository or external client
```

Routes handle transport, controllers orchestrate, services own framework-free
business logic, and repositories or clients own I/O. Use async database and
network APIs, dependency injection, and existing factories. Preserve public
APIs and response shapes unless explicitly changed. Resolve all changed-file
HARD findings; address WARN findings only when caused by the change or safely
inside scope.

Update durable docs only for public APIs, service boundaries, data models, auth,
integration contracts, deployment, or other observable behavior. Put local
docs in `apps/<service>/docs/` and shared contracts in `docs/`.

## Git and safety

Validation does not authorize Git actions.

- Do not branch, commit, or push unless requested. Push always requires explicit
  instruction; never bypass hooks without explicit approval.
- Never commit secrets or real `.env` files, or overwrite user work.
- Never delete or recreate the external `ollama` volume. Use repository
  Makefiles for the stack and Ollama; Redis remains required.
- Do not re-add `supabase/` or `legacy/`, remove `docker-bin/docker`, touch the
  empty `providers/`, or modify `airbyte-destination-embedding/` unless required.

## Completion

Report the outcome, important files, checks actually run, and remaining risk.
Do not report routine reads or raw logs.
