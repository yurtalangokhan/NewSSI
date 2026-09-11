# Deferred architecture & code-quality work

This document tracks items that were identified during the `codebase-simplification`
spec but are intentionally **deferred** — either because they are risky enough to
need characterization/tests first, or because they require per-component manual
review that a mechanical codemod cannot safely perform. They are NOT blocking the
architecture gate for the files already remediated, but they remain open findings
in the full-tree (`--all`) report and should be scheduled as follow-up work.

## Documentation automation

The service docs now keep human-readable API contracts under
`apps/<service>/docs/api.md`. Add a shared OpenAPI export command for FastAPI
services so generated schema artifacts can be refreshed consistently and kept
out of routine planning context.

## Source

- Spec: `.tmp/codebase-simplification/design.md`
- Gate: `scripts/quality/check_architecture.py`
- Reports: `.tmp/codebase-simplification/tasks/task-ARCH-T1-report.md`,
  `.tmp/codebase-simplification/tasks/task-AS-4-final-report.md`,
  `.tmp/codebase-simplification/tasks/task-TIER2-web-report.md`

---

## AGENT-SERVICE

### AS-3 (risky portion) — `service/AuthService.py` FastAPI dependency extraction
- **Finding:** `service/AuthService.py` imports `HTTPException` and `status` from
  FastAPI and raises them directly from the service layer (delivery-framework
  leakage into `service/`). 649 LOC, a 102-line method, cyclomatic complexity 198.
- **Why deferred:** High risk. Extracting the HTTP dependency requires a
  characterization test suite first (the method is large and complex). The
  non-risky parts of AS-3 (route/controller thinning) were completed in AS-4.
- **Plan:** Write characterization tests around `AuthService`, then introduce a
  domain exception type and translate it at the controller boundary.

### AS-CLIENT-SHIMS — service-layer external client compatibility shims
- **Finding:** `service/AirbyteApiClientService.py` and
  `service/AuthorizationClient.py` remain as compatibility re-export shims for
  the canonical `integrations/airbyte_api_client.py` and
  `integrations/authorization_client.py` modules. Several production call sites
  and test monkeypatch paths still import the old service-layer names.
- **Why deferred:** Low-to-medium risk because it is mostly import migration, but
  it touches datasource, schedule, auth, and persona paths plus tests.
- **Plan:** Migrate all callers to `integrations.*`, update monkeypatch targets,
  delete the two shims, and run the full agent-service gate.

### AS-USER-SERVICE-CLIENT — user-service client boundary
- **Finding:** `service/UserServiceClient.py` is a real external client still
  housed in the service layer. It is imported by services, controllers, an
  integration module, and the user-memory domain path.
- **Why deferred:** Higher risk than a shim deletion. The move needs a boundary
  design so domain code depends on a port instead of a concrete client.
- **Plan:** Add a domain/application port, move the concrete HTTP client to
  `integrations/`, inject it at the application boundary, and characterize auth,
  persona, and memory behavior first.

### AS-GITHUB-MCP-AGENT — standalone GitHub MCP agent disposition
- **Finding:** `agents/github_mcp_agent/github_mcp_agent.py` is not registered in
  the FastAPI static registry or `langgraph.json`, but it has dedicated unit
  tests and may represent a product capability decision rather than dead code.
- **Why deferred:** Deleting it would remove a tested capability without a clear
  replacement or product decision.
- **Plan:** Decide whether GitHub MCP is a built-in recipe, a dynamic-agent
  template, or unsupported. If unsupported, delete the module and its tests in
  the same TDD cleanup task.

### AS-KEYCLOAK-ADMIN-SHIM — inert Keycloak admin compatibility shim
- **Finding:** `integrations/keycloak_admin.py` is an inert compatibility shim
  (admin token helper always returns `None`, so profile lookups always return
  `None`). `service/AuthService.py` still imports `get_keycloak_user_profile`
  from it. Identity resolution flows through `user-service` and token claims.
- **Why deferred:** Low risk, but removal touches the auth identity path and its
  tests; the shim is documented with a removal note and exempted from the
  Keycloak boundary gate.
- **Plan:** Remove the shim module and its `AuthService` import, update any
  callers and tests, and run the full agent-service gate.

### AS-DOMAIN-HTTP-HOTSPOTS — domain-layer HTTP calls
- **Finding:** `domain/ollama/repository.py` and `domain/providers/service.py`
  perform concrete HTTP calls from the domain package.
- **Why deferred:** Existing architecture hotspots; not expanded during the
  observability work.
- **Plan:** Treat provider integrations as adapter candidates and introduce
  domain ports in a later refactor.

---

## WEB (Tier 2 remainder)

### WEB-RAW-HTML-REMAINDER — raw `<button>`/`<input>`/`<img>` + `Text` conflicts
- **Finding:** 50 web files still contain raw HTML/UI primitives flagged by the
  gate:
  - **39 files** with `<button>` / `<input>` / `<img>` (mechanical swap to
    `Button` / `InputTypeIn` / `PreviewImage` is unsafe — see report).
  - **10 files** that import or define a local `Text` component under a
    conflicting name, so the `<p>`/`<h*>` → `<Text as="...">` codemod could not
    add the refresh-components import.
  - **1 `.ts` false positive** (`hooks/useFederatedOAuthStatus.ts`) — `<h3>` in a
    JSDoc comment; gate should exclude `.ts` from the raw-HTML rule.
- **Why deferred:** The refresh-components `Button` hardcodes `type="button"` and
  applies its own size/variant classes; `InputTypeIn`/`PreviewImage` have different
  prop surfaces. Each file needs a per-component decision, not a bulk codemod.
- **Plan:** Triage the 39 button/input/img files by component; for each, choose
  the refresh-components equivalent (with correct variant) or document a justified
  exception. Resolve the 10 `Text` conflicts by renaming the local component or
  migrating to refresh-components `Text`. Fix the gate to skip `.ts` files (or
  leave the comment as-is).

---

## RAG-SERVICE

### RAG-0 — `PERF401` in `langconnect/api/documents.py`
- **Finding:** Lines 102 and 246 use an explicit list-comprehension-in-call
  (`list(...)` / `[...]`) where a generator would avoid a temporary list. WARN-only
  (performance), not blocking.
- **Why deferred:** Micro-optimization; no correctness impact. Safe to leave.

---

## TOOLS-SERVICE

### TS-0 — `java` category in `tests/tools-service/test_registry.py`
- **Finding:** A test references a `java` tool category that does not exist in the
  registry (stale test expectation). WARN-only (test correctness, not architecture).
- **Why deferred:** Test-data cleanup; does not affect the production gate.

---

## Notes

- All HARD findings in files touched by the `codebase-simplification` work have
  been resolved (ARCH-T1, AS-4, Tier 2 mechanical web pass). The items above are
  either WARN-only or require risky/manual work and are tracked here so they are
  not lost.
- The architecture gate runs in `--changed` mode in the pre-commit/pre-push hooks,
  so only files you edit are checked. These deferred items will not block commits
  to unrelated files, but they remain visible in `make architecture-check`
  (full-tree report) and should be scheduled.
