# Web index

Use this file only for work under `apps/web/`. Root `AGENTS.md` owns the
workflow; this file routes frontend work to code, tests, and documentation.

## Ownership and source map

The web app is Next.js 16 with App Router, the Atlas refresh component system,
and the `@atlas/opal` workspace.

```text
src/app/                  App Router pages and routes
src/components/           Shared components
src/refresh-components/   Atlas components
src/refresh-pages/        Page-level components
src/icons/                Only icon source
src/hooks/                Hooks
src/lib/                  Shared utilities and infrastructure
src/lib/api/domains/      Domain API, endpoints, hooks, server operations, tests
src/lib/api/http/         Central browser and server HTTP transport
src/lib/pageRoutes.ts     Typed catalog of all page endpoints for navigation
src/providers/            React context providers
src/layouts/              Layouts
src/ee/                   Enterprise features
src/i18n/                 Translations
src/interfaces/, types/   Type contracts
lib/opal/                 Shared @atlas/opal workspace
tests/                    Jest and Playwright tests
```

## Task routing

Use the narrowest row that matches the task.

| Change | Start in | Direct tests |
|---|---|---|
| Page or route | `src/app/`, then `src/refresh-pages/` | Matching page tests |
| Shared UI | `src/refresh-components/` or `lib/opal/` | Co-located component tests |
| Domain data hook | `src/lib/api/domains/<owner>/hooks.ts` | Domain hook and consumer tests |
| Shared UI hook | `src/hooks/`, `src/lib/hooks/` | Matching hook/component tests |
| Provider or state | `src/providers/` | Provider and consumer tests |
| API integration | `src/lib/api/domains/<owner>/api.ts`, `endpoints.ts`, optional `hooks.ts` or `server.ts` | Domain `tests/` and affected consumers |
| End-to-end flow | Relevant page and components | Matching `tests/e2e/` spec |

## Documentation routing

Open only a document whose condition matches the change.

| Condition | Document |
|---|---|
| Current frontend folders, domain owners, page data flow, or modularization state | `docs/frontend-map.md` |
| Backend API boundaries, gateways, rendering, routing, or workspace changes | `docs/architecture.md` |
| Test project or coverage selection is unclear | `docs/testing.md` |
| Startup, environment, or deployment changes | `docs/runbook.md` |
| App ownership is unclear | `docs/overview.md` |
| Detailed code or design-system convention is needed | `STANDARDS.md` |

## Backend API contract — HARD

Every application-backend request must preserve this boundary:

- UI code calls only a named domain API or domain hook.
- Browser paths, backend targets, and path builders live only in
  `src/lib/api/domains/<owner>/endpoints.ts`.
- Domain `api.ts` uses `apiRequest`; domain `server.ts`, route handlers, and
  gateway adapters use `backendRequest` or `proxyToBackend`.
- A route uses `endpoint.backend` or a domain-owned gateway target builder.
  Never construct backend origins, service prefixes, API versions, or backend
  paths in pages, components, hooks, or routes.
- Only the gateways in
  [`docs/architecture.md`](docs/architecture.md#approved-dynamic-gateways) are
  allowed. Adding another gateway exception requires updating that document
  and `scripts/domain-architecture/scanner.mjs`.
- Native backend `fetch` and legacy request helpers are forbidden outside the
  central transport layer.

Server-side consumers use named domain `server.ts` operations with shared
request context. Prefer a complete `{ method, browserPath, backend }`
descriptor for dedicated browser/backend route pairs. Gateway-backed
operations may use a browser path plus a domain-owned target builder, but all
path ownership remains in `endpoints.ts`.

Run `npm run check:domain-architecture` after changing backend access. See
[web architecture](docs/architecture.md#backend-operation-flow) for the full
flow, approved gateways, examples, and exceptions.

## Page navigation workflow

- Add every new `src/app/**/page.tsx` endpoint to `src/lib/pageRoutes.ts`.
- Use `pageRoutes` for internal links, page-oriented `href` values,
  `router.push()`, `router.replace()`, and pathname comparisons.
- Use builder functions for dynamic segments and encode every segment.
- Keep query parameters, API paths, redirects, and external URLs separate from
  the catalog; build query values with `URLSearchParams` at the call site.
- Update `src/lib/pageRoutes.test.ts` and run
  `src/lib/pageRoutesGuard.test.ts` after navigation changes.

## Invariants

- Use absolute project imports and existing SWR fetching patterns.
- Define React components with `function`, props with interfaces, and compose
  classes with `cn()`.
- Use project color tokens without built-in Tailwind colors or `dark:` variants.
- Use project primitives instead of raw controls or visible text elements.
- Import icons only from `src/icons/`.
- Browser modules must not transitively import domain `server.ts` or
  `next/headers`.
- No `index.ts` barrels, compatibility facades, or forwarding shims; import
  the specific domain file you use.
- Treat `lib/opal/` changes as shared-surface changes.

## Test scope

Use a focused Jest path inside quiet task wrappers. At spec completion, include
all affected Jest projects and Playwright specs only when the user flow changed.
Use existing test utilities and fetch-mocking conventions. Full `make validate`
runs only through the push wrapper.
