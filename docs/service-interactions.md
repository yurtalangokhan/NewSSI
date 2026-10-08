# Service Interactions & Request Flows

## System topology

Application JSON routes are moving to service-local `ResponseModel` contracts:
`statusCode`, `message`, `data`, and nullable `error`. Each route group migrates
with its browser and service clients. Follow the
[response migration checklist](response-model-migration.md) for completed
routes, remaining groups, and streaming/protocol decisions.

```
Browser (Next.js 16)
    │
    ▼
Gateway (APISIX implementation, port 8000)
    │
    ├──► user-service (port 8090)    ──► PostgreSQL
    │       Users, organizations         Keycloak Admin API
    │
    ├──► agent-service (port 8080)   ──► PostgreSQL
    │       Chat, agents, threads         LangGraph checkpoints
    │       Personas, providers           MinIO (files)
    │       Datasources, schedules        In-process connectors (sync)
    │                                    MCP provider services
    │
    ├──► rag-service (port 8083)     ──► PostgreSQL (metadata)
    │       Collections, documents        Milvus (vectors)
    │       Graph RAG, search             Neo4j (knowledge graph)
    │
    └──► tools-service (port 8001)   ──► PostgreSQL
            MCP tools (44 tools)         Working directory
```

---

## Connector tools in chat

The agent editor selects saved datasource instances and permitted read
operations. Agent-service persists these references on the persona and carries
the selected persona ID to tools-service through trusted MCP context.

Tools-service resolves each invocation through the internal APISIX route
`/internal/agent-service/api/v1/internal/connector-tools/resolve`. Agent-service
rechecks the caller's agent access and current saved assignment before resolving
the saved connector configuration. Tools-service then executes the bounded read
against the configured source. The model receives data and sanitized errors;
it does not receive connection credentials.

Agent-service does not hold connector configurations. It reads the decrypted
configuration of the assigned datasource from user-service's internal API and
translates it into the shape the tools-service adapter expects. The credential
response is never stored in the idempotency replay cache.
Ingestion and RAG retrieval remain separate from these live reads.

## Authentication flow

### External user (browser → APISIX)

The configured Keycloak realm is `agenticai-v1`. Browser login uses its
`web-client`; Gateway introspects with `gateway-client` and requests UMA
decisions from the corresponding `user-service-client`,
`agent-service-client`, `rag-service-client`, or `tools-service-client`.
Gateway HTTP paths retain the `/user-service`, `/agent-service`,
`/rag-service`, and `/tools-service` prefixes.

```
User → Browser → Web auth handler → Gateway → Keycloak (OIDC redirect)
    ↓
Keycloak issues tokens → Gateway sets HttpOnly cookies through Web
    ↓
API call includes JWT → Gateway introspects token directly with Keycloak
    ↓
Gateway requests Keycloak UMA decisions for the route's permissions
    ↓
Gateway forwards trusted identity headers (x-gateway-token, x-gateway-user-id,
x-gateway-email, x-gateway-username, x-gateway-roles)
    ↓
Owning service trusts those headers → resource/tenant checks
```

Backend services do not authenticate. They hold no JWKS client, verify no token
signature, accept no API key, and have no development or anonymous fallback. A
request that does not carry a valid `x-gateway-token` is rejected with 401, so
reaching a service port directly is not a way around route authorization.
Gateway strips every `x-gateway-*` header from inbound requests before it runs.

### Service-to-service (internal)

```
Service A → Gateway /internal/{service}/... → Service B
               ↓
User bearer: introspection and route authorization with Keycloak
Machine-only: verify INTERNAL_SERVICE_TOKEN at Gateway and backend
```

### Auth dependency chain

External password login must reach the configured external identity provider.
If Keycloak returns the internal realm's login form, Gateway rejects the request
before submitting credentials. An enabled gateway alias alone does not provision
the identity provider in a newly created Keycloak realm.

```
require_user
  └─ resolve_gateway_identity(headers, INTERNAL_SERVICE_TOKEN)
      ├─ valid x-gateway-token + x-gateway-user-id → that user
      ├─ valid x-internal-service-token            → "internal-service"
      │                                              (+ x-user-id delegation)
      └─ otherwise                                 → 401

require_permission("X")  → require_user → checks via user-service
```

The forwarded `Authorization: Bearer` token is never used to authenticate. It is
passed to user-service so permissions resolve for the same principal.

### Compact token authorization model

JWTs carry role markers, not the full permission catalog. The login client
(`KEYCLOAK_CLIENT_ID`, `web-client` by default) has no "Full scope allowed": the bootstrap maps exactly the
platform realm roles `system-admin`, `enterprise-admin` and `enduser` into its
tokens (`realm_access.roles`), which is all Gateway reads from them (primary
role, `x-gateway-roles`). Feature bundles (service-client roles), roles created
at runtime and Keycloak's built-in roles do not appear in the token; the
authorization services evaluate them from the user model (`fetchRoles`).
Backend services must not treat token roles as fine-grained permissions.

Gateway authorizes the route before forwarding it, and is the only place route
authorization happens. Backend checks continue to protect resource-level
operations through user-service.

User-service also projects direct agent and collection assignments into
Keycloak instance resources. Assignment, role, organization-status, and deletion
changes reconcile the managed policies under a shared Redis lock. Group policies
use current membership without extending access to child groups. Inactive
organizations do not contribute grants. User-service reconciles existing SQL
assignments before it becomes ready; projection failures deny access.

```text
Gateway route/method → Keycloak UMA permission decision → allow or deny

Backend endpoint require_permission("entity:action")
  -> service calls user-service
  -> user-service resolves effective Keycloak roles, including group inheritance
  -> assigned composite roles expand feature bundles
  -> feature bundles expand permissions
  -> user-service returns allow or deny
```

This keeps tokens small and lets administrators change feature-bundle
permissions without adding fine-grained claims to the JWT.

Keycloak owns composite realm roles, client feature roles, permission metadata,
and user/group assignments. Users can hold multiple roles. The API's primary
role is a projection of those assignments; no local identity table mirrors it.
The `system-admin` role retains its wildcard behavior. Login, refresh, and OIDC
callbacks preserve existing Keycloak identities and assignments.

Every role is addressed by its immutable Keycloak role `id`. This covers the
`/roles/{role_id}`, `/coarse-roles/{role_id}`, and user role-assignment
endpoints. Composite role `role_ids` contain Keycloak feature-role IDs, and
`role_names` provides their display names. The web admin UI selects, submits,
and displays roles by ID.
Feature-bundle and composite-role responses include `is_builtin` from the
Keycloak `agentic.builtin` attribute. The web admin UI hides Delete only for
roles marked `true`; a missing attribute or `false` means custom. User-service
rejects deletion only for roles marked `true`. Attribute-free client roles on
configured service clients appear as custom bundles with zero permissions;
Keycloak's internal `uma_protection` role is omitted.
Permission-catalog entries expose the configured `service_client` ID for their
owning service. The feature-bundle editor enables only matching client
permissions and preserves previously assigned cross-client grants on Save.

User-service remains the user-management and internal API facade. Gateway owns
login, callback, refresh, logout, token verification, and route authorization.
User-service startup configures
the login client and administrator-managed identity attributes, and performs the
configured administrator bootstrap. Startup does not synchronize a SQL role
catalog into Keycloak or modify an existing administrator's profile or role
assignments. Complete the guarded
[identity cutover](../apps/user-service/docs/runbook.md#keycloak-identity-cutover)
before starting this version against a pre-cutover database.

User IDs equal Keycloak subjects, and organization IDs equal Keycloak group IDs.
Application settings, keys, memories, audit records, resource grants, agent
ownership, and collection ownership retain these external IDs. They do not
resolve through local user or organization rows.

### OIDC redirect and logout invariants

OIDC browser auth spans the web app, Gateway, Redis, and Keycloak. Keep the
runtime redirect and logout behavior consistent across those boundaries.

- The web logout route calls Gateway logout, clears browser auth cookies,
  and then redirects OIDC users to the Keycloak front-channel logout endpoint.
  Backchannel logout invalidates the server-side Keycloak session, but it can't
  remove cookies owned by the Keycloak origin from the user's browser.
- Register exact callback URLs on the Keycloak login client and in
  `GATEWAY_ALLOWED_REDIRECT_URIS`. Gateway rejects callbacks outside this
  allowlist. Browser proxy handlers preserve OIDC state, PKCE binding cookies,
  and response cookies across authorization and callback requests.
- Keycloak client updates must merge `redirectUris`, `webOrigins`, and
  `post.logout.redirect.uris` with existing values. Do not replace admin-managed
  entries from environment or runtime values.
- Treat login, logout, callback redirect, and browser cookie changes as
  security-sensitive behavior. Cover redirect URI merging, post-logout redirect
  handling, cookie creation and clearing, and open redirect validation with
  regression tests.
- Admin pages use server-side authentication first, then load fine-grained route
  permissions in `UserProvider`. Web admin menus and pages don't authorize by
  hardcoded role names. They use user-service's effective permissions, which
  user-service resolves from the user's assigned roles, direct role
  permissions, and service coarse-role permissions. Permission fetch failures
  must not grant admin access; completed permission checks that deny the route
  trigger the `403` page.
- Validate changed auth behavior through focused task wrappers, followed by
  affected spec tests. If services are running, verify the browser flow through
  Gateway. Full service validation belongs to the push tier.

### Organization workspace

The organization page calls user-service for its resource workspace. User-service
authorizes the actor's organization scope and target membership, then requests
the caller-visible agent or collection catalog through Gateway. It returns
resources and direct assignments together. Agent-service and RAG-service retain
ownership of their catalogs. The frontend submits assignment changes to the
existing scoped user-service PUT endpoint.

This composition does not recurse: catalog authorization can read user-service
permission APIs, but those APIs do not invoke organization workspace composition.

---

## Idempotency contract

Mutating HTTP requests use the shared `idempotency` middleware in
agent-service, user-service, rag-service, and tools-service. Clients that retry
an operation must send an `Idempotency-Key` header. Reusing the same key for the
same principal and the same request replays a cached response when replay is
safe.

The middleware stores a normalized request fingerprint that includes method,
path, query string, content type, and request body hash. Reusing a key for a
different fingerprint returns `409 idempotency_key_reused`. Reusing a key across
different principals also returns `409`; the principal scope is derived from
authenticated headers and is stored as a hash, not as the raw identity value.

Idempotency-Key values are validated before any Redis interaction: keys must be
1–255 characters from `[A-Za-z0-9._-]`. A malformed or overlong key returns
`400 idempotency_key_invalid` without touching the store.

Redis availability is handled per policy mode:

- Optional modes fail open — if Redis is unreachable the request passes through
  without idempotency handling so a store outage does not take down the service.
- Required modes return `503 idempotency_store_unavailable` when Redis is down,
  because the key is mandatory for safe side-effect handling.

While a request is in flight, the owning lock is renewed periodically
(`pexpire` every `lock_ttl / 3` seconds) so long-running requests are not
evicted by an inflight timeout. Replays are byte-for-byte: cached bodies are
stored base64-encoded (`metadata_version=2`) so binary payloads round-trip
exactly, and responses larger than `max_cache_body_size` (default 1 MiB) are
not cached at all. Responses replayed from cache strip `set-cookie`,
`www-authenticate`, `server`, and `x-powered-by` headers so a replay cannot
re-issue session cookies or challenge headers.

Services classify mutating endpoints into these policy categories:

- `excluded`: the middleware ignores the request.
- `optional_replay`: a key is optional, but a supplied key enables replay and
  conflict detection.
- `required_replay`: a key is required by default
  (`IDEMPOTENCY_ENFORCE_REQUIRED_KEYS=true`); successful deterministic responses
  can be replayed.
- `domain_required`: a key is always required because duplicate side effects are
  risky.

`domain_required` endpoints include streaming LLM calls, MCP tool execution,
uploads, graph builds, model pulls, email sends, datasource sync, and destructive
admin cleanup. Tools-service direct `/mcp` is the transport-level exception:
FastMCP streamable-HTTP sessions send multiple protocol POSTs over one logical
session, so `/mcp` honors supplied keys for replay and conflict detection but
doesn't reject missing keys. If the middleware cannot replay the response, such
as for SSE streams or other non-cacheable responses, it marks the key as
completed without replay. A retry with that key returns `409` instead of
starting the side effect again.

A `domain_required` route whose handler can safely run again for the same
request may declare `rerun_after_failure` in its policy. A run that answered
`429` or `5xx`, or raised, then frees the key instead of closing it, and a
retry with the same key runs again. A run that succeeded is still replayed and
a run in flight still answers `409 idempotency_request_in_progress`. Only
rag-service's connector record ingestion declares it (see
[Connector configurations and syncs](#connector-configurations-and-syncs)).

The web frontend forwards incoming `Idempotency-Key` values through mutating
Next.js API routes, excluding login, refresh, logout, and OIDC browser auth
flows. `authenticatedFetch` also auto-generates a key for mutating, non-auth
requests that did not supply one, generating it once per operation so a retry
after token refresh reuses the same key. UI actions that start retryable
operations create UUID keys. A visible retry of the same operation must reuse
the same key, while a new operation must create a new key.

Local host-based services use `REDIS_HOST=localhost`; Compose-hosted services
use `REDIS_HOST=redis`. Redis listens on port `6379` and persists data in the
`redis-data` volume.

---

## Error response contract

Backend services and Next.js API routes return one error envelope for non-2xx
responses:

```json
{
  "error": {
    "code": "request.invalid",
    "message": "Invalid request.",
    "details": {},
    "field_errors": [],
    "request_id": null
  }
}
```

The HTTP status controls transport behavior. `error.code` is the stable
programmatic contract for clients and localization, while `error.message` is a
safe fallback for display. Frontend callers use the central parser in
`apps/web/src/lib/api/errors.ts` or `getErrorMsg` from
`apps/web/src/lib/fetchUtils.ts`; new code should not parse `detail` directly.

Idempotency middleware returns this envelope itself because it may reject a
request before FastAPI handlers run.

Application-owned Python exception definitions live in
`packages/error-contract/src/error-contract/`. Common HTTP errors are exported
from `error_contract`; domain families are grouped in `composition`, `domain`,
`agent`, `connectors`, `identity`, `lifecycle`, `idempotency`, and `resilience`. Compatibility
imports in services refer to the same class objects. Python and SDK exceptions
remain their original types and are translated at the owning integration boundary.

Database connection and timeout failures return 503; other database execution
failures return 500. Upstream timeouts return 504, invalid upstream responses and
upstream authentication failures return 502, and unavailable or throttled
upstream services return 503. A user's authentication failure remains 401.
Missing resources and conflicts use 404 and 409 instead of generic 400 errors.

Errors can carry `message_key` and `message_params`. HTTP handlers and stream/tool
adapters render these through the existing i18n module and shared English/Turkish
catalogs. Locale selection follows query `lang`/`locale`, `X-Language`, then
`Accept-Language`. Responses identify their language with `Content-Language`;
idempotency replays preserve the original body and language. Frontend transport
keeps the status, stable code, field errors, details, and request ID, and uses
localized fallbacks for empty or unavailable upstream responses.

Expected failures use specific catches. General catches remain only where an
unknown failure must be isolated, such as transaction rollback, cleanup,
background jobs, plugins, and final stream or tool responses. These boundaries
must preserve cancellation and must not expose raw driver exception messages.
SSE and MCP keep their existing wire shapes.

---

## Request lifecycle: chat message

```
1. POST /agent-service/api/v1/chat/messages
   │
   ▼
2. APISIX routes to agent-service:8080
   │
   ▼
3. chat_controller.send_message()
   │  ├─ Reads Gateway-established identity
   │  ├─ Fetches LLM provider + API key (decrypted from DB)
   │  ├─ Resolves persona/agent definition
   │  ├─ Creates LangGraph run with thread + checkpointer
   │  └─ Returns StreamingResponse (SSE)
   │
   ▼
4. LangGraph agent executes:
   │  ├─ Calls LLM (OpenAI, Anthropic, Ollama, etc.)
   │  ├─ Calls MCP tools via tools-service (web search, calculator, code, etc.)
   │  ├─ Calls RAG service for vector search (document chunks)
   │  ├─ Calls RAG service for graph search (knowledge graph)
   │  ├─ Reads/writes user memories via user-service
   │  └─ Streams events (token, reasoning, tool_calls) back via SSE
   │
   ▼
5. Frontend renders streaming response in chat UI
```

### Resumable chat runs

A chat run is not tied to the browser connection that started it. agent-service
executes each accepted message in a supervisor-owned task and writes every SSE
frame to a replayable Redis event log. HTTP responses only subscribe to that
log, so closing the tab, reloading, or losing the network never stops the run.
Only an explicit Stop, the run timeout, or process loss ends it early.

The web app and agent-service share this contract:

| Call | Contract |
|---|---|
| `POST /api/v1/chat/messages` | Unchanged request. The SSE response adds `id: <seq>` lines, a `run_started` packet first, and a `run_end` packet before the final `[DONE]`. The `Idempotency-Key` header becomes the run's `client_request_id`. |
| `409 chat_run.active` | The thread already has a running answer. The error envelope names the holder in `error.details.run_id`; the web app shows a toast and attaches to that run instead of rendering an error. A send that cannot be registered (Redis down) answers `503 chat_run.unavailable`. |
| `GET /api/v1/chat/sessions/{session_id}/active-run` | Returns the session's in-flight run (`run_id`, `input_preview`, `client_request_id`) or `null`. |
| `GET /api/v1/chat/sessions` | Each listed session carries `has_active_run`: whether a run is still generating its answer. The sidebar marks continuing chats with it (no lookup per row) and marks a newer answer than `last_accessed_at` as unread. |
| `POST /api/v1/chat/sessions/{session_id}/seen` | Advances the session's read watermark (`last_accessed_at`) to now. The client calls it when it has actually shown a run's finished answer, so the sidebar's unread dot clears without reopening the chat. Owner-checked. |
| `GET /api/v1/chat/runs/{run_id}/events` | Replays the run from `after` or `Last-Event-ID`, then follows it live. It sends one `caught_up` packet (no `id:`, never stored) when replay has drained and the stream turns live. A stream that ends while still replaying (a finished run, `resync`) sends none. It answers `404` for an unknown, expired, or foreign run and sends a `resync` packet when the position was trimmed. |
| `POST /api/v1/chat/stop-chat-session/{session_id}` | Owner-checked. It stops the run on whichever instance owns it. The optional `client_request_id` query names the send being stopped, so a Stop pressed before the run is registered still prevents it from starting. No token frame is logged after a recorded Stop. |

The web client re-attaches in these cases:

- **Network drop mid-stream:** `resumableChatStream` reconnects with
  exponential backoff: a random point in the upper half of a step that doubles
  from 500 ms to 10 s, so tabs dropped together don't reconnect together. It
  gives up after eight attempts without progress. Each re-attach replays from the start and
  skips packets it already delivered, so the parser's turn and tool
  bookkeeping sees the whole stream without duplicates. The `caught_up` packet
  tells the client where that replay ends: replayed packets render at once,
  only packets after it animate as live output.
- **POST fails before `run_started`:** the client attaches only when the active
  run's `client_request_id` matches the send's idempotency key.
- **Page load, tab visible again, or back online:** the chat page asks for the
  active run and renders it under its user message.
- **Replay no longer available:** on `404` or `resync`, the client shows the
  persisted conversation instead.

Unmounting, navigating away, and aborting a stream never call the stop
endpoint. Only the user's Stop does. For run states, Redis keys, and
configuration, see the agent-service
[architecture](../apps/agent-service/docs/architecture.md) and
[API](../apps/agent-service/docs/api.md) docs.

### Chat session timestamps

Chat session ordering uses conversational activity, not access time. The thread
row stores these timestamp meanings:

- `created_at` is the row creation time.
- `updated_at` tracks durable metadata or content bookkeeping. Read access
  doesn't update it.
- `last_message_at` is set when the backend accepts a user message for an
  authorized chat session. It is set before response streaming starts, so
  provider failure, partial streaming, and client cancellation don't roll it
  back.
- `last_accessed_at` records that a user opened or viewed the chat. It doesn't
  affect Recents or project chat ordering.

Recents and project chat lists order sessions by
`COALESCE(last_message_at, created_at) DESC`, with `thread_id DESC` as the
stable tie-breaker. Older frontend responses that don't include
`last_message_at` can temporarily fall back to `time_updated`, but explicit
`last_message_at: null` means the session has no accepted user-message activity
and orders by `time_created`.

### Document draft generation

Document/spreadsheet tool calls (`create_document`, `create_spreadsheet`,
`edit_document`, `rewrite_document`) drive a `document_generation_*` /
`generated_file` packet sequence, additive to the base contract every one of
those tools already had (see agent-service `docs/api.md`, "Document output
tools" and "Document drafts (versioned editing)"):

- `document_generation_start` / `document_generation_progress` /
  `document_generation_end` carry `tool_name`, `operation`
  (`create`/`edit`/`rewrite`), `document_id` (once known), `filename`,
  `format`, and `phase`. `phase` is one of `writing` (the model is still
  streaming the tool call's arguments), `applying` (an edit's `old_str`/
  `new_str` ops are being matched against the current draft — carries
  `applied`/`total` and, on completion, the block-level `changes` list),
  `validating` (Mermaid fences are checked) or `rendering` (the output file
  is produced and stored). `document_generation_end` additionally carries
  `status` (`success`/`error`/`incomplete`) and `error`.
- The `generated_file` packet (and its chat-history reconstruction) gains
  optional fields carried straight from the tool's JSON payload when present:
  `document_id`, `revision_no`, `revision_count`, `operation`, `summary`,
  `stats`, `diagram_check`. A pre-draft tool result (or an old checkpoint)
  omits them and old clients keep working unchanged.
- Emitted order for an edit: `document_generation_start` (`phase=writing`) →
  writing progress → `applying` progress (start, then once per completed
  edit) → `validating` → `rendering` → `generated_file` →
  `document_generation_end` (`status=success`).

The chat request body also accepts an optional `document_context:
{document_id, revision_no}`, sent while the document panel is open. A
malformed value is rejected as a 422 (`chat.invalid_document_context`) rather
than silently dropped, since dropping it would look like the "edit this
document" request worked when the agent never saw it.
`agent_runner_coordinator._active_document` projects it into
`configurable["active_document"]` for the run — never into the `HumanMessage`
text, so it never pollutes conversation history and needs no mid-conversation
system message (some providers reject those). `list_documents` marks the
matching entry `"active": true` and sorts it first.

### Frontend app routing

The web app uses path-based `/app` routes for durable chat, agent, and project
identity. Query parameters are reserved for compatibility and temporary command
state during migration.

- `/app` opens a new default chat.
- `/app/chats/{chat_id}` opens an existing chat session.
- `/app/agents/{agent_id}` opens a new chat with an agent preselected.
- `/app/projects/{project_id}` opens a project workspace.
- `/app/shared/{chat_id}` remains the shared-chat route.

Legacy `/app?chatId=...`, `/app?agentId=...`, and `/app?projectId=...` links
still parse to the same app state and are replaced with the canonical path on
the client. Chat URLs don't carry `projectId`; project context is derived from
the chat session and project membership data.

---

## Request lifecycle: document upload + RAG

```
1. Frontend uploads file to agent-service
   │
   ▼
2. agent-service stores in MinIO, creates datasource
   │
   ▼
3. POST /agent-service/api/v1/datasources/{id}/sync  →  sync job started
   │
   ▼
4. agent-service connector runtime (packages/connector-py):
   │  ├─ Read the datasource's connector configuration from user-service
   │  ├─ Read the selected streams from the source in batches
   │  └─ Turn each record into text + metadata
   │
   ▼
5. POST /rag-service/api/v1/datasources/{id}/records  →  rag-service, per batch:
   │  ├─ Split into chunks
   │  ├─ Generate embeddings (Ollama/OpenAI)
   │  └─ Insert into Milvus (vector DB), then delete the chunks an earlier
   │     write stored for the same records
   │
   ▼
6. POST /rag-service/api/v1/collections/{id}/documents  →  rag-service
   │  ├─ Parse and chunk same way
   │  ├─ Generate embeddings
   │  ├─ Upsert to Milvus
   │  └─ Store metadata in PostgreSQL
   │
   ▼
7. User searches → POST /rag-service/api/v1/collections/{id}/documents/search
   │  ├─ Generate query embedding
   │  ├─ Cosine similarity search in Milvus
   │  └─ Return top-k chunks with scores
```

---

## Request lifecycle: knowledge graph build

```
1. POST /rag-service/api/v1/graph/build  { collection_id }
   │
   ▼
2. rag-service starts background task:
   │
   ├─ 1. Fetch all chunks from Milvus for this collection
   ├─ 2. LLMGraphTransformer extracts entities + relations
   │      (Ollama or OpenAI)
   ├─ 3. Upsert Entity nodes to Neo4j
   ├─ 4. Upsert Relationship edges to Neo4j
   └─ 5. Update build progress in PostgreSQL
   │
   ▼
3. POST /graph/search  { query, collection_id }
   │
   ├─ Vector search in Milvus (cosine similarity)
   ├─ Graph search in Neo4j (BM25 fulltext)
   ├─ Reciprocal Rank Fusion (RRF) scoring
   └─ Return nodes + edges + formatted context
```

---

## Request lifecycle: knowledge search page

The **Search** mode of the web app searches every collection you can read. The
browser calls rag-service through the web `/api/rag/*` gateway, which forwards
to APISIX and rag-service's `/api/v1/search*` routes.

```
1. GET  /api/rag/search/sources            → rag-service /api/v1/search/sources
   └─ readable collections, connector info, and whether each has a graph

2. POST /api/rag/search { query, kind, limit, filters }
   │                                        → rag-service /api/v1/search
   ├─ vector retrieval per readable collection (Milvus)
   ├─ graph retrieval per graph collection (Neo4j), unless kind is vector
   ├─ Reciprocal Rank Fusion over the ranked lists
   └─ hits + merged subgraph + facets + per-collection counts

3. POST /api/rag/search/graph/neighborhood { collection_id, node_ids, depth }
   └─ merged ego graph for "Expand neighbors" and graph depth

4. GET  /api/rag/collections/{id}/documents/{file_id}/chunks
   └─ passage preview, surrounding passages, and the full document
```

"Expand neighbors" reaches one hop further per press on the same node (depth
1 to 3); the browser sends the hop count as `depth`.

---

## Knowledge evidence contract

Knowledge searches return two things: the text the model reads and a
`KnowledgeEvidence` payload the chat UI renders as a card. The payload lists
the chunks or the subgraph the model received, so you can see what an answer
was based on.

The contract (v1) lives in tools-service (`src/knowledge/evidence/`) and agent-service
(`src/schemas/knowledge_evidence/`), one copy per producer, guarded by
`docs/contracts/knowledge-evidence.v1.json`.
The models are immutable and self-bounding: at most
20 chunks of 4,000 characters, 60 graph nodes, and 120 edges; every edge
endpoint is a node, and secret-like properties are dropped.

```text
tools-service database_search / graph_search
   ├─ content            → numbered model text ("[n] (document)\ncontent")
   └─ structuredContent  → KnowledgeEvidence v1
agent-service ToolsServiceToolGateway → ToolResult.structured
   └─ KnowledgeEvidenceArtifactPolicy
        ├─ inserts a knowledge_evidence row (thread-scoped)
        └─ ToolMessage.artifact = {"knowledge_evidence_id": "<uuid>"}
agent-service stream / history
   └─ custom_tool_delta {response_type: "knowledge_retrieval",
                         evidence_id, data: KnowledgeEvidence}
```

Flow retrieval nodes (`DocumentSearch`, `KnowledgeBase`, `GraphSearch`,
`GraphEntitySearch`, and `GraphNeighborhood`) build the same payload in
agent-service and stream it as a tool step of their stage.

The checkpoint and the flow timeline store only the evidence id. Agent-service
fills `data` from the `knowledge_evidence` table when it streams the packet and
when it rebuilds history, reading only rows of the requested thread. A packet
whose row is gone keeps `data: null`, and the UI shows that the details are no
longer available.

## Service dependency map

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend    │────►│    APISIX      │────►│  Keycloak    │
│  (Next.js 16) │     │  (port 8000) │     │  (OIDC IdP)  │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
       ┌──────────┐  ┌──────────┐  ┌──────────┐
       │  User    │  │  Agent   │  │   RAG    │
       │ Service  │  │ Service  │  │ Service  │
       └────┬─────┘  └────┬─────┘  └────┬─────┘
            │             │             │
            │        ┌────▼────┐        │
            │        │ Tools   │        │
            │        │ Service │        │
            │        └─────────┘        │
            ▼             ▼             ▼
       ┌─────────────────────────────────────┐
       │         PostgreSQL (shared)          │
       └─────────────────────────────────────┘
            │             │             │
            ▼             ▼             ▼
       ┌──────────┐  ┌──────────┐  ┌──────────┐
       │  MinIO   │  │  Milvus  │  │  Neo4j   │
       │ (files)  │  │(vectors) │  │ (graph)  │
       └──────────┘  └──────────┘  └──────────┘
```

### Service-to-service calls

| Caller        | Callee                  | Purpose                                                                         | Method                                 |
| ------------- | ----------------------- | ------------------------------------------------------------------------------- | -------------------------------------- |
| agent-service | user-service            | Permission checks, batched persona owner lookup, user lookup, and memories CRUD | HTTP + internal token                  |
| agent-service | rag-service             | RAG collections proxy                                                           | HTTP + caller token                  |
| agent-service | rag-service             | Agent knowledge availability checks for selected document and graph collections | HTTP + internal token                  |
| agent-service | tools-service           | MCP tool execution                                                              | HTTP + JWT                             |
| agent-service | user-service            | Stored connector configurations (create, read, update, delete)                  | HTTP + internal token                  |
| tools-service | rag-service             | Knowledge retrieval for `database_search` and `graph_search` (`POST /api/v1/retrieval`) | HTTP + internal token + delegated user |
| rag-service   | user-service            | Permission checks for Gateway-established identity                          | HTTP + forwarded JWT or internal token |
| tools-service | user-service            | Permission resolution                                                           | HTTP + internal token                  |
| rag-service   | Ollama/OpenAI           | LLM calls for graph extraction                                                  | HTTP (outbound)                        |
| agent-service | Ollama/OpenAI/Anthropic | LLM inference                                                                   | HTTP (outbound)                        |

---

## Internal vs external routing

### External (through APISIX)

```
Browser → APISIX:8000/agent-service/api/v1/*  → agent-service:8080
Browser → APISIX:8000/user-service/api/v1/*   → user-service:8090
Browser → APISIX:8000/rag-service/api/v1/*    → rag-service:8083
Browser → APISIX:8000/tools-service/mcp       → tools-service:8003
```

### Internal (service-to-service)

Backend clients read `INTERNAL_USER_SERVICE_URL`,
`INTERNAL_RAG_SERVICE_API_URL` and `INTERNAL_TOOLS_SERVICE_URL` for these routes.
Tools-service connector resolution reads `INTERNAL_AGENT_SERVICE_URL`, whose
base includes `/internal/agent-service/api/v1`. Unprefixed service URLs belong
to web runtime or public metadata and are not backend fallback addresses.

```
Service → http://apisix:8000/internal/user-service  → user-service:8090
Service → http://apisix:8000/internal/rag-service   → rag-service:8083
Service → http://apisix:8000/internal/tools-service/mcp → tools-service:8003
```

Machine-only calls present `X-Internal-Service-Token` to Gateway. User-scoped
calls forward the caller's bearer token to Gateway for Keycloak authorization.
Gateway then establishes trusted identity for the downstream service.

---

## Key integration patterns

### Pattern 1: Permission check

```
Service A wants to check if User X has permission "chat:send":
  GET /api/v1/internal/users/{user_id}/permissions
  Header: X-Internal-Service-Token
  ← Returns { "permissions": ["chat:send", "chat:read", ...] }
```

### Pattern 2: User lookup by Keycloak ID

```
Service A has a Keycloak subject ID and needs its application user view:
  GET /api/v1/internal/users/by-keycloak-id/{keycloak_id}
  Header: X-Internal-Service-Token
  ← Returns user dict with user_id equal to the subject, email, and role
```

Persona creation uses this identity resolution path before persistence. New
ownership references use the authenticated Keycloak subject. The cutover command
reconciles historical local IDs before local identity tables are removed.

### Pattern 3: User memory recall

```
Agent needs to recall user facts:
  GET /api/v1/internal/users/{user_id}/memories/recall
  Header: X-Internal-Service-Token
  ← Returns ["User likes Python", "User works at Acme Corp", ...]
```

### Pattern 4: MCP tool execution

```
Agent needs to run a tool:
  Agent Service
    ↓ POST /api/proxy/mcp/execute { tool_name, arguments, url }
    ↓
  ProxyController
    ↓ MCP client call
  Tools Service
    ↓ Execute tool code
    ← Return result
```

Trusted binding references (`database_search.collection_ids`,
`connectors.persona_id`) use dotted keys on both services. On the wire each key
travels as one `x-binding-ref-<key>` header with `.` encoded as `__`
(`x-binding-ref-database_search__collection_ids`); tools-service decodes it
back to the dotted key. The codec is `binding_header_name` and
`binding_key_from_header` in `trusted.py`; agent-service's
`trusted_context.py` mirrors the encoder. Each knowledge tool reads only its
own `<tool>.collection_ids` key.

### Pattern 5: Organization-scoped access management

User-service is the policy authority for organization membership and direct
agent or collection grants. Enterprise administrators can manage the entire
tree; actors with organization action permissions and active unit-manager
assignments can manage their assigned units and descendants. Only global
administrators can appoint unit managers; delegated membership assignments and
role changes are limited to End User. Organization membership roles exclude
System Admin and Enterprise Admin.

The organization membership UI uses the same Keycloak role assignments as the
admin Users page. The unchanged `role_in_org` request/response field is a
compatibility alias for the selected platform role; the legacy membership
column was removed by migration 0046. Updates invoke User Service's single-role
setter and update Keycloak platform assignments, primary-role metadata, and the
effective-access cache. Unit Manager aliases resolve to the catalog name.
Active membership identifies the units managed by a Unit Manager. A role change
applies across the user's units; removing membership does not remove that role.
Delegates can select End User only for unassigned or existing End User targets,
and cannot replace privileged roles or change their own role.

```text
Organization page selects Unit B
  GET /api/v1/organizations/{unit_b}/management-capability
  GET /api/v1/organizations/{unit_b}/users
  GET /api/v1/permissions/organizations/{unit_b}/targets/{type}/{id}/resources/{resource_type}
  PUT /api/v1/permissions/organizations/{unit_b}/targets/{type}/{id}/resources/{resource_type}
    -> user-service validates manager scope
    -> user targets must be active members of Unit B
    -> direct grants are synchronized and audited
```

Resource grants do not inherit from parent units. This allows directors and
subunits to use different agents and collections. Membership and role mutation
endpoints apply the same subtree check, so a unit manager cannot change an
ancestor or unrelated branch. The model permits one root only; creating a
second root or moving a unit to root is rejected.

Removing a membership locks the user and performs membership deletion plus
orphan permission cleanup in one user-service transaction. Direct user grants
survive transfers between units while another active membership exists. When
the final active membership is removed, all user-target resource permissions
are deleted; organization grants, grants for other users, and audit history are
preserved.

### Pattern 6: Shared organization visual designer

The Organization page owns the hierarchy, selection, membership data,
management capability, and existing mutation callbacks. The full-screen visual
designer reuses that state and those callbacks; it doesn't introduce separate
organization, membership, or resource-access workflows.

```text
Administrator opens the organization designer
  Browser GET /api/user-service/organizations/tree
    -> Next.js user-service proxy forwards GET /api/v1/organizations/tree
    -> scoped hierarchy is laid out locally, showing two levels initially
    -> expansion reveals children and recomputes the compact view
    -> org:move enables dragging inside the scoped tree, excluding scope roots

Administrator enables Show users in either organization view
  Browser GET /api/user-service/organizations/members
    -> Next.js user-service proxy forwards GET /api/v1/organizations/members
    -> one response groups active direct members by organization ID
    -> textual and visual trees reuse the same session-scoped preference
    -> users render inside their owning unit without becoming hierarchy nodes

Administrator selects a node
  Browser GET /api/user-service/organizations/{org_id}/management-capability
  Browser GET /api/user-service/organizations/{org_id}/users
  -> Details and Users reuse the page's existing mutation callbacks
  -> Access owns its scoped permission PUT through OrganizationAccessPanel
     at /api/user-service/permissions/organizations/{org_id}/targets/{type}/{id}/resources/{resource_type}
  -> a successful Access PUT asks the page to revalidate the hierarchy/counts

Administrator reveals an organization search result
  -> loads each ancestor's complete direct-child list through the scoped children endpoint
  -> reuses cached complete lists and commits the hierarchy once all levels are ready
  -> expands the selected path, shows its siblings with descendants collapsed
  -> focuses the selected node; child counts reflect complete sibling lists

Administrator switches the diagram to vertical or horizontal view
  -> changes local orientation and fits the visible tree without server writes

Administrator drops a node onto its new parent and confirms
  Browser POST /api/user-service/organizations/{org_id}/move
    -> Next.js user-service proxy forwards POST /api/v1/organizations/{org_id}/move
    -> hierarchy changes only through this explicit action
```

Mutation controls remain disabled until the selected organization's capability
request completes. Read-only nodes stay selectable, and the actor can pan,
zoom, fit the view, and inspect the hierarchy without mutation access.
The optional member request remains disabled until **Show users** is enabled.
Membership mutations revalidate the selected-unit membership list and the bulk
member map while the option is active.
When the hierarchy is empty, the designer shows root creation only when the
authenticated permission set includes `org:create`, which is the same
permission enforced by the user-service create route.

Coordinates are temporary rendering state. Keyboard input cannot replace automatic
positions. Dropping a node onto a valid parent opens a confirmation; approval sends
the existing move request, guarded by `org:move` and backend scope checks. Cancelling
restores the automatic position. Closing preserves the selected organization without
flushing coordinates. The layout endpoint and `organization_layouts` table have been
removed; migration 0048 leaves hierarchy, memberships, and access grants intact.

### Pattern 7: RAG proxy

```
Agent needs to list RAG collections:
  Agent Service
    ↓ GET /api/proxy/rag/collections
    ↓
  ProxyController
    ↓ HTTP call
  RAG Service
    ← Return collections list
```


## Organization grants in chat

User-service owns direct agent and collection grants. Agent-service and RAG-service use the configured versioned permission endpoints and resolve local user identities. The strongest applicable direct grant or active organization membership grant determines access. Catalogs and execution or retrieval enforce the same required permission; stale selections and failed permission lookups do not authorize access.

Organization action permissions remain separate from unit scope. Active unit-manager assignments determine delegated roots, while authoritative global administrators retain global access. The web organization tree starts at the highest permitted roots, and organization APIs enforce the same boundaries.

## Connector configurations and syncs

A datasource's connector configuration is owned by the user who created it and
stored by user-service in `user_connector_configs`, the whole document sealed
under `CONNECTOR_CONFIG_ENCRYPTION_KEY`. Agent-service keeps only the reference
(`datasource_connections.config_id` and `owner_user_id`).

```
agent-service ──► user-service   /internal/user-service/api/v1/internal/users/{user_id}/connector-configs[/{id}]
                                 X-Internal-Service-Token only; a user JWT is refused
agent-service ──► rag-service    /internal/rag-service/api/v1/datasources/{id}/records   (one call per batch)
agent-service ──► rag-service    DELETE /internal/rag-service/api/v1/datasources/{id}/records   (the datasource is deleted)
```

Only the single-item GET returns the decrypted configuration. Create, update,
and delete answer with metadata, so no credential reaches an idempotency replay
cache. The routes are published on the internal Gateway path only.

Syncs run in agent-service: the connector runtime reads the configuration,
streams the source's records in batches to rag-service, and records jobs and
incremental checkpoints in `connector_sync_jobs` and `connector_sync_state`.
Schedules are rows of `sync_schedules`; the scheduler claims a due slot with a
compare-and-set on `next_run_at`, so one replica starts each scheduled run.
Deleting a datasource first asks rag-service to drop the collection's Milvus
table (`DELETE .../datasources/{id}/records`, while the collection row still
names it); a 404 means there is nothing to drop, any other failure leaves the
datasource in place.

### Record ingestion contract

One batch is one `POST .../datasources/{id}/records` with the idempotency key
`connector-sync.<datasource>.<job>.<stream digest>.<batch index>`.

```json
{
  "documents": [
    {"content": "id: 7\ntitle: Invoice", "metadata": {"stream": "invoices", "id": 7},
     "record_key": "3f786850e387550fdab836ed7e6dc881de23001b"}
  ],
  "clear_existing": false
}
```

- `documents[].record_key` (optional, 40 lowercase hex characters) names the
  record at its source. Agent-service sends the SHA-1 of the stream name and
  the record's primary-key values (the primary key the sync was configured
  with, else the one the source declares), or of the whole record when the
  stream has no primary key or the record no value for it.
- rag-service keeps one version per record key: it stores the key on every
  chunk (`metadata._record_key`), inserts the new chunks, and then deletes the
  chunks an earlier write stored under the same key. A record with a primary
  key is replaced when it changes; a record without one only when it comes
  again unchanged. A document without a key is appended. Of two documents with
  the same key in one request, the last is stored.
- The answer is `{"chunks_indexed", "chunk_char_total", "chunk_token_total",
  "chunks_replaced"}`. `chunks_replaced` counts the deleted chunks; agent-service
  takes them out of the datasource's chunk statistics.
- Retry: the route declares `rerun_after_failure`. A batch that failed with
  `429` or `5xx` is sent again under the same key (three attempts per batch)
  and runs again; because the new chunks are inserted before the old ones are
  deleted, a failed run removes nothing and the retry leaves one version. A
  batch whose answer was lost is replayed. A batch refused with another `4xx`
  keeps its key (`409 idempotency_key_reused`) and fails the job.
- A job that runs again after a failed or interrupted one sends the records
  after its last checkpoint under new idempotency keys; the record keys make
  that a replacement, not a second copy.

## User-service JSON response contract

User-service application JSON endpoints return `statusCode`, `message`, `data`, and optional
`error` containing `code` and a localized `message`. The real HTTP status
matches the body. This includes internal permission, identity, memory, settings,
and audit calls. Clients must validate the envelope before reading `data`.
They must preserve error status/code/message and must not treat a successful
HTTP transport as an authorization grant without checking the permission data.

Agent, RAG, and tools adapters unwrap at their user-service boundaries; browser
domain APIs do the same while BFF gateways forward the envelope. Authentication
cookies keep their existing transport behavior. CSV export and Prometheus
metrics retain their file/text protocols. Health readiness retains HTTP 503 on
failure. Memory and organization 204 acknowledgements become HTTP 200 with
null data. Runtime regression checks remain pending.


## RAG JSON response contract

All 41 RAG application JSON registrations use the same service-local fields as
user-service: `statusCode`, `message`, `data`, and nullable `error`. HTTP status
matches the body. Collection create preserves 201 and upload-job start preserves
202; collection/graph delete acknowledgements return 200 with null data.
Idle upload/graph status is also null data. Health, readiness and graph-health
keep native top-level payloads and existing HTTP 200/503. Auth, validation, idempotency, and unexpected errors use
the envelope and preserve existing transport headers.

Browser knowledge domain APIs and agent RAG clients validate status and unwrap
objects, arrays, or null. The RAG BFF gateway stays transparent. Agent ingestion
uses the versioned RAG graph client with an idempotency key; its collection
proxy preserves the caller token and projects data into its existing collection
wrapper. Public error messages come from error_contract EN/TR locale keys.
Raw metrics, files, streaming, and sockets retain their transport protocols.
Runtime regression verification remains pending.


## Agent response contract

All 196 agent application JSON routes return the local ResponseModel with
statusCode, message, data, and nullable error (code/message). Route -> controller
-> service preserves typed exception propagation; the route renders the central
locale key for the caller. Named web domain APIs and server consumers, AgentClient,
internal connector resolution, and the connector runtime's rag-service calls unwrap data and
check statusCode against HTTP status. Creation uses 201 where already declared;
discard-draft acknowledgement uses 200/null. External connector responses remain
in their native protocols.

Agent streaming uses StreamEventModel serialization with existing SSE payload
fields, data-only framing, keepalives, and completion sentinels. After stream
start, failures carry localized error.code/error.message and content; before
start, the normal JSON error handler applies. Health/readiness/metrics and raw
file transport remain native. Runtime verification remains pending.
