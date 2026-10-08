# Frontend code map

Use this guide to locate the current frontend implementation. Paths are
relative to `apps/web/` and describe the repository's current architecture.

## Completion status

All 15 domains have `api.ts` and `endpoints.ts`. Named browser and server
operations use the existing central transport. Request hooks belong to their
domain; shared UI hooks remain outside it. The source scanner enforces the
covered structural boundaries; it does not prove runtime response or error
parity. See the [web architecture](architecture.md#backend-operation-flow) for
the normative request flow and approved gateways.

Project contracts now have one owner in `projects/types.ts`. Model-provider
and embedding cache keys come from the respective domain `endpoints.ts` files.

A page does not need its own domain. Pages compose multiple domains and shared
providers. Redirect-only and static pages might not request data at all.

## Where to find frontend code

Start with the kind of change you want to make:

| You need | Current location |
| --- | --- |
| URL entry, page composition, layout, or loading boundary | `src/app/` |
| Main product screen implementation | `src/refresh-pages/` |
| Shared UI | `src/refresh-components/`, `src/components/` |
| UI primitives | `lib/opal/` |
| Page sections and modals | `src/sections/` |
| Layout composition | `src/layouts/` and `src/app/**/layout.tsx` |
| Shared React context | `src/providers/` |
| Domain data access | `src/lib/api/domains/<domain>/` |
| Central HTTP, parsing, and error contracts | `src/lib/api/http/` |
| Shared route forwarding | `src/lib/api/proxy.ts` |
| Server cookie context | `src/lib/api/server-context.ts` |
| Backend origin configuration | `src/lib/env/`, exposed through `src/lib/settings.ts` |
| Navigation and route access helpers | `src/lib/navigation/` |
| Auth infrastructure and permissions | `src/lib/auth/` |
| UI-level and shared hooks | `src/hooks/`, `src/lib/hooks/` |
| Enterprise UI | `src/ee/`, `src/app/ee/` |
| Translations and icons | `src/i18n/`, `src/icons/` |
| Shared non-domain contracts | `src/interfaces/`, `src/types/` |
| Domain contract tests | `src/lib/api/domains/<domain>/tests/` where present |
| UI tests | Co-located component/page test directories |
| Test helpers and browser tests | `tests/` |

UI implementation is currently split across several existing folders. The
domain migration organizes API ownership; it does not turn the entire UI into
one feature-folder hierarchy. Shared hooks and utility files outside domains
are not necessarily backend access code.

## Domain directory

Every row refers to `src/lib/api/domains/<domain>/`. These are practical starting
points, not claims that every page has only one dependency.

| Domain | Data responsibility | UI areas to start from |
| --- | --- | --- |
| `session` | Current user, login, signup, verification, logout | `app/auth/`, app layouts |
| `preferences` | Personal and chat preferences, source selection | `app/app/settings/`, chat controls |
| `notifications` | Notification reads and dismissal | Sidebar, avatar and notification popovers |
| `agents` | Agent/persona definitions, flows, labels, availability | `app/app/agents/`, `app/app/flows/`, `app/admin/agents/` |
| `chat` | Conversations, sharing, history, chat files | `app/app/chats/`, `app/app/shared/`, `refresh-pages/AppPage.tsx` |
| `documents` | Authored document drafts: detail, revisions, by-file, user edit, restore, export | `sections/document-panel/`, `app/app/message/messageComponents/renderers/` |
| `projects` | Projects and project context | `app/app/projects/`, project controls |
| `craft` | Craft configuration and operations | `app/craft/v1/` |
| `datasources` | Connectors, credentials, indexing | `app/admin/connectors/`, `connector/`, `indexing/`, `add-connector/` |
| `knowledge` | Documents, collections, chunks, search, graph, document sets | `app/admin/documents/`, `kg/`, search configuration |
| `tools` | Tools, MCP, OpenAPI, code interpreter | `app/admin/actions/`, `app/tools/playground/`, MCP callback |
| `model-providers` | LLM and image/vision provider operations | `app/admin/configuration/llm/`, `image-generation/` |
| `integrations` | Slack, Discord, federated sources, provider OAuth | `app/admin/bots/`, `discord-bot/`, `federated/`, OAuth callbacks |
| `access` | Users, groups, organizations, roles, API keys | `app/admin/users/`, `roles/`, `organizations/`, `api-key/`, `app/ee/admin/groups/` |
| `billing` | Billing and subscription data | `app/admin/billing/`, `app/ee/admin/billing/` |
| `system` | System information, mail, settings, usage and analytics | `app/admin/systeminfo/`, `system-settings/`, mail configuration, `app/ee/admin/performance/` |

Some screens intentionally span owners: embeddings uses knowledge and model
providers; organization access can combine access and knowledge; chat combines
agents, model providers, projects, preferences, and session. Shared navigation
also introduces session and notification dependencies.

## Files inside a domain

Use the file matching the responsibility. Optional files are present only where
needed; the current directories are not identical templates.

| File | What you find there |
| --- | --- |
| `endpoints.ts` | Request paths, dynamic path builders, backend descriptors |
| `api.ts` | Named browser operations, request payloads, response/error conversion |
| `hooks.ts` | Domain React state, SWR keys, pagination, polling |
| `server.ts` | Named server-side data operations |
| `types.ts`, descriptive `*-types.ts` files | Domain request/response contracts |
| `tests/` | Domain tests where present; coverage is not uniform across domains |
| Descriptive helpers | For example, agents `selectors.ts`, `availability.ts`; datasource `indexing.ts` |

## How a page gets data

Browser data requests follow this ownership chain:

```text
src/app/.../page.tsx -> screen/component
  -> domains/<owner>/hooks.ts or api.ts
  -> domain endpoints.ts + api/http/browser.ts (apiRequest)
  -> dedicated Next.js API route or approved dynamic gateway
  -> domain backend descriptor or domain-owned target builder
  -> api/proxy.ts / api/http/server.ts (backendRequest)
  -> backend
```

Not every `/api/...` request has its own physical route file. Follow the actual
route or catch-all when tracing it. The complete gateway list, ownership rules,
examples, and external-fetch exception are documented under
[approved dynamic gateways](architecture.md#approved-dynamic-gateways).

Server-rendered consumers take a different entry point:

```text
server page/layout -> domains/<owner>/server.ts
  -> shared server-context when cookies are required
  -> backendRequest -> backend
```

The HTTP modules own transport. Domain APIs own operation contracts. Hooks own
React fetching state. Components own rendering and interaction. Keep new
consumer code free of backend URLs and direct transport calls.

## Trace concrete screens

These examples show where to begin reading:

1. System information: `src/app/admin/systeminfo/page.tsx` calls
   `system/api.ts:getBackendVersion`. The `/api/version` route uses
   `systemServerBackend.version` and forwards to the agent `/version` endpoint.
2. Document lists: `knowledge/hooks.ts:useDocuments` calls
   `knowledge/api.ts:fetchCollectionDocuments`. The hook owns pagination and
   the SWR key; `knowledge/endpoints.ts` owns the path builder.
3. Signed-in server UI: `session/server.ts:getCurrentUserSS` resolves the user
   using shared server request context.
4. Settings entry: `src/app/app/settings/page.tsx` redirects to
   `/app/settings/general`; inspect that destination for the screen's data.
5. Knowledge search: the header **Chat / Search** switch sets
   `AppModeProvider`'s mode. In search mode on a new session,
   `refresh-pages/AppPage.tsx` renders
   `sections/knowledge-search/KnowledgeSearchMode.tsx`. The page state lives in
   `sections/knowledge-search/state/useKnowledgeSearchController.ts`, which
   calls `knowledge/hooks.ts:useKnowledgeSearch`,
   `useKnowledgeSearchSources`, and `useKnowledgeNeighborhoods`. Pure logic
   (reducer, paging, graph merging, viewport math) is in
   `sections/knowledge-search/model/`.
6. Document drafts panel: the chat message renders a generated file card
   (`app/app/message/messageComponents/renderers/DocumentCard.tsx`), which calls
   `sections/document-panel/openGeneratedFile.ts`. That opens
   `sections/document-panel/DocumentPanel.tsx` inside the resizable
   `DocumentWorkspace` mounted by `refresh-pages/AppPage.tsx`. Draft data comes
   from `documents/api.ts` + `documents/hooks.ts`, UI state from
   `app/app/stores/useDocumentPanelStore.ts`, and the pure block/word diff from
   `lib/documents/diff/`. Every send attaches `document_context` read from that
   store in `hooks/useChatController.ts`.

To trace any other page, follow its imported screen, then its domain hook/API
import, then the named operation and endpoint. Include ancestor layouts and
providers: their data requests do not have to appear in the page source itself.

## Validation boundaries

Run `npm run test:domain-architecture` for scanner fixtures and
`npm run check:domain-architecture` for source boundaries. The scanner reports
dynamic gateways and external requests separately. Its same-target/method
groups are review candidates, not proof of duplicate behavior.
