# Deferred architecture & code-quality work

This document tracks items that were identified during the `codebase-simplification`
spec but are intentionally **deferred** — either because they are risky enough to
need characterization/tests first, or because they require per-component manual
review that a mechanical codemod cannot safely perform. They are NOT blocking the
architecture gate for the files already remediated, but they remain open findings
in the full-tree (`--all`) report and should be scheduled as follow-up work.

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

### ASC-1W — frontend agent catalog adoption
- **Finding:** Web still imports agent catalog data from a legacy module path
  rather than the consolidated catalog.
- **Why deferred:** Folded into the ASC workstream; depends on the catalog
  consolidation landing first. Low priority for the gate (no HARD finding).

### ASC-2D — delivery cutover
- **Finding:** Some routes still wire agents through a deprecated delivery path.
- **Why deferred:** Part of the ASC workstream; needs the new delivery path to
  stabilize.

### ASC-3 through ASC-7 — agent-composition package simplification
- **Finding:** `agent_composition/` has package-structure and import-path debt
  (tracked in `../agent-service-composition/plan.md`).
- **Why deferred:** Separate, higher-risk workstream; not in scope of the
  codebase-simplification gate beyond the `RuntimePolicyConfig` re-export fix
  applied during AS-4.

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
