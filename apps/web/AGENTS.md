# Web index

Use this file only for work under `apps/web/`. Root `AGENTS.md` owns the
workflow; this file routes frontend work to code, tests, and documentation.

## Ownership and source map

The web app is Next.js 16 with App Router, the Onyx refresh component system,
and the `@onyx/opal` workspace.

```text
src/app/                  App Router pages and routes
src/components/           Shared components
src/refresh-components/   Onyx components
src/refresh-pages/        Page-level components
src/icons/                Only icon source
src/hooks/                Hooks
src/lib/                  Utilities and fetchers
src/providers/            React context providers
src/layouts/              Layouts
src/ee/                   Enterprise features
src/i18n/                 Translations
src/interfaces/, types/   Type contracts
lib/opal/                 Shared @onyx/opal workspace
tests/                    Jest and Playwright tests
```

## Task routing

Use the narrowest row that matches the task.

| Change | Start in | Direct tests |
|---|---|---|
| Page or route | `src/app/`, then `src/refresh-pages/` | Matching page tests |
| Shared UI | `src/refresh-components/` or `lib/opal/` | Co-located component tests |
| Hook or client data | `src/hooks/`, existing SWR caller | Matching hook/component tests |
| Provider or state | `src/providers/` | Provider and consumer tests |
| API integration | Existing fetcher and interfaces | Tests mocking the exact endpoint |
| End-to-end flow | Relevant page and components | Matching `tests/e2e/` spec |

## Documentation routing

Open only a document whose condition matches the change.

| Condition | Document |
|---|---|
| Rendering, routing, or workspace boundary changes | `docs/architecture.md` |
| Test project or coverage selection is unclear | `docs/testing.md` |
| Startup, environment, or deployment changes | `docs/runbook.md` |
| App ownership is unclear | `docs/overview.md` |
| Detailed code or design-system convention is needed | `STANDARDS.md` |

## Invariants

- Use absolute project imports and existing SWR fetching patterns.
- Define React components with `function`, props with interfaces, and compose
  classes with `cn()`.
- Use project color tokens without built-in Tailwind colors or `dark:` variants.
- Use project primitives instead of raw controls or visible text elements.
- Import icons only from `src/icons/`.
- Do not hardcode backend URLs or ports.
- Treat `lib/opal/` changes as shared-surface changes.

## Test scope

Use a focused Jest path inside quiet task wrappers. At spec completion, include
all affected Jest projects and Playwright specs only when the user flow changed.
Use existing test utilities and fetch-mocking conventions. Full `make validate`
runs only through the push wrapper.
