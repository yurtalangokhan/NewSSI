# Web architecture

The web app uses Next.js App Router and the Atlas design system. Keep page
composition, data fetching, reusable UI, and low-level utilities separated.

## Layers

Use these layers to find request ownership without changing UI composition.

```text
UI layer          pages, components, providers
                  src/app/**/page.tsx, src/components, src/sections
Domain layer      request ownership per product domain
                  src/lib/api/domains/<domain>/
Transport layer   central HTTP clients
                  src/lib/api/http/browser.ts  -> apiRequest()
                  src/lib/api/http/server.ts   -> backendRequest()
Route proxy layer Next.js API routes forwarding to backend services
                  dedicated route or approved dynamic gateway
                  -> backendRequest() / proxyToBackend()
```

## Backend operation flow

Every browser backend operation follows one visible path:

```text
page / component / provider
  -> domain hook (stateful or cached) or domain action (plain call)
  -> src/lib/api/domains/<domain>/api.ts
  -> apiRequest()
  -> dedicated Next.js API route or approved dynamic gateway
  -> backendRequest() or proxyToBackend()
  -> configured backend service
```

Server-rendered consumers use the server path:

```text
Server Component / layout
  -> src/lib/api/domains/<domain>/server.ts operation
  -> backendRequest() (shared server-cookie context)
  -> configured backend service
```

## Domain layout

Backend origins come from four environment variables: `AGENT_SERVICE_URL`,
`RAG_SERVICE_URL`, `USER_SERVICE_URL`, and `TOOLS_SERVICE_URL`.
`src/lib/env/` validates them at boot, `appSettings` exposes typed values, and
the gateway guard requires every service URL to use the configured APISIX
origin and service route prefix. Domain descriptors specify complete endpoint
paths. `backendRequest` joins the selected service base and endpoint while
preserving auth, headers, query values, and request bodies. The web MCP proxy
uses `TOOLS_SERVICE_URL`; `MCP_INTERNAL_URL` remains a separately validated
internal gateway route. `WEB_DOMAIN` is the frontend origin. See the
[runbook](runbook.md#startup) for the required gateway paths.

Fifteen domains own all backend requests:
`session`, `agents`, `chat`, `projects`, `craft`, `notifications`,
`preferences`, `datasources`, `knowledge`, `tools`, `model-providers`,
`integrations`, `access`, `billing`, `system`.

```text
src/lib/api/domains/<domain>/
  endpoints.ts   endpoint descriptors: frontend path, backend service/path,
                 safe path/query builders
  api.ts         request functions: body construction, apiRequest() calls,
                 response parsing, errors, fallback values
  types.ts       optional domain DTOs
  hooks.ts       optional SWR, polling, pagination, optimistic hooks
  server.ts      optional server-only operations; never imported by browser code
  tests/         domain request-contract tests
```

## Ownership rules

For browser/backend pairs, prefer a named operation in the domain catalog:

```ts
export const chatEndpoints = {
  sendMessage: {
    method: "POST",
    browserPath: "/api/chat/send-chat-message",
    backend: { service: "agent", path: "/api/v1/chat/send-chat-message" },
  },
} as const;
```

Browser APIs read `browserPath` and `method`; backend adapters read `backend`.
Keep browser and backend encoding explicit when their contracts differ.
Do not infer missing counterparts or change cache keys to fit this shape. A
gateway-backed operation may instead pair its browser path with a domain-owned
target builder because runtime segments are part of its protocol. In both
forms, `endpoints.ts` remains the only path owner.

Keep each responsibility in its existing layer:

- `endpoints.ts` is the only owner of endpoint URLs and backend target
  metadata. One descriptor per endpoint; never represent one endpoint as a
  constant, descriptor, builder, and inline literal at the same time.
- `api.ts` is the only place that calls `apiRequest`. It owns body
  construction, parsing, and fallbacks.
- `hooks.ts` owns cache and UI request state (SWR keys, polling, optimistic
  updates) and calls domain APIs only.
- `server.ts` owns server-only operations and the shared server-cookie
  context. Browser modules must not transitively import `server.ts` or
  `next/headers`.
- Route files declare their public Next.js route segment and call
  `backendRequest()` with backend target metadata from the owning domain
  descriptor. They never build backend origins, service prefixes, or backend
  paths. Approved dynamic gateways use a domain-owned target builder and
  central transport.
- No `index.ts` barrels, compatibility facades, forwarding shims, or empty
  files. Consumers import the specific file they use.
- Central transport owns idempotency, auth refresh, and environment lookup.
  Domain operations preserve their response parsing, error contracts, and
  operation-specific header overrides; don't duplicate transport machinery.

## Approved dynamic gateways

A dynamic gateway is an infrastructure route that forwards an open-ended
service or protocol namespace rather than one named domain endpoint family. It
is not the default way to add an operation. These are the complete approved
gateway exceptions:

| Gateway | Domain resolver | Purpose |
| --- | --- | --- |
| `src/app/api/[...path]/route.ts` | `accessEndpoints.userServiceProxy` or `agentsEndpoints.apiProxy` via `src/lib/api/routeBackendUrl.ts` | Compatibility gateway for the existing user and agent route families |
| `src/app/api/agent/[...path]/route.ts` | `agentsEndpoints.agentProxyTarget` | Agent-service route family |
| `src/app/api/langgraph/[...path]/route.ts` | `agentsEndpoints.agentProxyTarget` | LangGraph SDK dynamic protocol |
| `src/app/api/rag/[...path]/route.ts` | `knowledgeEndpoints.ragProxyTarget` | RAG route family, including multipart and streaming requests |
| `src/app/api/user-service/[...path]/route.ts` | `accessEndpoints.userServiceProxy` via `src/lib/api/userServicePath.ts` | User-service route family |
| `src/app/mcp/[[...path]]/route.ts` | `toolsEndpoints.mcpProxy` | MCP base endpoint and protocol subpaths |

Catch-all syntax alone does not make a route a gateway. The
`agent-definitions`, `agent-groups`, `flow-components`, and `user/projects`
catch-all routes are ordinary domain routes: each resolves its target through
one named builder in the owning domain's `endpoints.ts`.

The gateways do not bypass the domain API boundary. Browser callers still use
a named domain API or hook, the domain owns the browser path and backend target
builder, and the gateway forwards through `backendRequest` or
`proxyToBackend`. Adding another catch-all requires an architecture decision,
an update to this list, and matching coverage in
`scripts/domain-architecture/scanner.mjs`.

A dedicated operation keeps both sides in one descriptor:

```text
domain api.ts -> endpoint.browserPath -> src/app/api/<operation>/route.ts
              -> endpoint.backend -> backendRequest -> backend
```

A gateway-backed operation keeps its runtime mapping in the same domain:

```text
domain api.ts -> endpoint browser path -> approved catch-all route
              -> domain target builder -> backendRequest/proxyToBackend
              -> backend
```

The only native-fetch exception is
`src/lib/sources.ts:fetchTitleFromUrl`, which retrieves a credential-free
external page title rather than calling an application backend. Downloads and
media may use domain-generated URLs with native browser navigation or loading;
their URL ownership still belongs to the domain endpoint catalog. Session
refresh may accept the deployment-provided `NEXT_PUBLIC_CUSTOM_REFRESH_URL`;
it is an external integration target and still delegates to `apiRequest`.

## Page navigation

`src/app/` is the source of truth for Next.js App Router endpoints.
`src/lib/pageRoutes.ts` is the typed catalog for referring to those pages from
application code. Add each new `page.tsx` endpoint to the catalog, and use the
catalog for internal links, page-oriented `href` values, client-side router
calls, and pathname comparisons.

Static entries are literal paths. Dynamic entries are builder functions that
encode every path segment. Keep query values outside the catalog and append
them with `URLSearchParams` at the call site. API paths, server redirects,
callback destinations, downloads, and external URLs remain separate because
they have different ownership and behavior.

Use `matchesRoute()` when a pathname can match either a catalog route or one
of its child segments. The matcher enforces segment boundaries, so a route
such as `/admin/billing-extra` does not match `/admin/billing`.

Update `src/lib/pageRoutes.test.ts` when the catalog changes. Run
`src/lib/pageRoutesGuard.test.ts` to detect raw page-navigation literals and
to receive file-and-line diagnostics for each violation.

## Admin page authorization

Admin navigation and page access use explicit `:view` permissions declared in
`src/lib/navigation/admin-routes.ts`. For example, `agent:view` opens the Agents
page, `datasource:view` opens Existing Connectors, and `provider:view` opens LLM
Models. Each separate menu has its own permission; detail and edit routes use
their parent page's permission through the same registry.

Store grants in Keycloak client-role `agentic.permissions` attributes. The
permission catalog discovers these values just like other permissions. Admin
and manager bundles receive appropriate page views; ordinary enduser bundles
receive no admin views. Assigning a view grants page access without granting
API read, create, update, or delete operations. API authorization continues to
check its existing action permissions at the gateway.

The server requires at least one enabled page view for admin-panel entry.
Server-rendered pages that load admin data check their own route's view grant
before fetching that data. The client guard checks the requested page and
hides its content while permissions load. Unknown admin routes deny access.
The existing system-admin wildcard continues to satisfy view permissions.

## Boundaries

Preserve the existing UI and import conventions:

- Use absolute imports with `@/` for application source and `@tests/` for test
  helpers.
- Use `@/refresh-components/` or `@opal/` components for inputs and controls.
- Use `@/icons/` as the only icon source.
- Use `Text` components for visible copy instead of raw heading or paragraph
  elements.
- Keep SWR data-fetching state in the owning domain's `hooks.ts`; components
  consume named hooks or API operations.

## Testing model

Test contracts at the layer that owns them:

- Consumer tests mock domain APIs or hooks, not `fetch`.
- Domain tests protect request contracts: URL, method, body, headers.
- Transport and route tests stay at their real boundaries.
- `pageRoutesGuard.test.ts` fails with file and line for any raw internal page
  literal in `Link`, page `href`, `router.push()`, or `router.replace()`.

See the [frontend code map](frontend-map.md) for current domain owners, file
responsibilities, page examples, and validation boundaries.
