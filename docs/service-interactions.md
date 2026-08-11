# Service Interactions & Request Flows

## System topology

```
Browser (Next.js 16)
    │
    ▼
Kong API Gateway (port 8000)
    │
    ├──► user-service (port 8090)    ──► PostgreSQL
    │       Auth, users, roles           Keycloak (OIDC)
    │
    ├──► agent-service (port 8080)   ──► PostgreSQL
    │       Chat, agents, threads         LangGraph checkpoints
    │       Personas, providers           MinIO (files)
    │       Datasources, schedules        Airbyte (sync)
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

## Authentication flow

### External user (browser → Kong)

```
User → Browser → Kong → Keycloak (OIDC redirect)
    ↓
Keycloak issues JWT → Browser stores in cookie
    ↓
Every API call includes JWT → Kong validates → forwards to service
    ↓
Service validates JWT locally or via user-service
```

### Service-to-service (internal)

```
Service A  ──►  X-Internal-Service-Token  ──►  Service B
                    ↓
              Matches INTERNAL_SERVICE_TOKEN env var
                    ↓
              Bypasses JWT auth, identifies as "internal-service"
```

### Auth dependency chain

```
require_auth_or_internal_service_token
  └─ get_current_user_id  (extracts from Bearer header or cookie)
      └─ returns "internal-service" for X-Internal-Service-Token

require_auth             → 401 if no user
require_admin            → require_auth → checks superuser or admin role
require_permission("X")  → require_auth → checks via user-service
```

### OIDC redirect and logout invariants

OIDC browser auth spans the web app, user-service, and Keycloak. Keep the
runtime redirect and logout behavior consistent across those boundaries.

- The web logout route calls user-service logout, clears browser auth cookies,
  and then redirects OIDC users to the Keycloak front-channel logout endpoint.
  Backchannel logout invalidates the server-side Keycloak session, but it can't
  remove cookies owned by the Keycloak origin from the user's browser.
- User-service must register runtime callback and post-logout redirect URIs
  before redirecting users to Keycloak. This supports local ports and deployed
  origins that differ from static bootstrap values.
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
  user-service resolves from the user's assigned role, direct role permissions,
  and service coarse-role permissions. Permission fetch failures must not grant
  admin access; completed permission checks that deny the route trigger the
  `403` page.
- Validate auth changes with `make -C apps/user-service validate`. When web
  logout or callback code changes, also run web lint, typecheck, and tests. If
  services are running, verify the browser flow through Kong.

---

## Request lifecycle: chat message

```
1. POST /agent-service/api/v1/chat/send-chat-message
   │
   ▼
2. Kong routes to agent-service:8080
   │
   ▼
3. chat_controller.send_message()
   │  ├─ Resolves user from JWT
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
3. POST /agent-service/api/v1/datasources/{id}/sync  →  Airbyte sync triggered
   │
   ▼
4. Airbyte reads source → writes to destination
   │  (airbyte-destination-embedding)
   ▼
5. POST /agent-service/api/v1/ingest/batch  →  agent-service ingest pipeline:
   │  ├─ Parse document (PDF, DOCX, CSV, etc.)
   │  ├─ Split into chunks (1000 chars, 200 overlap)
   │  ├─ Generate embeddings (Ollama/OpenAI)
   │  ├─ Upsert to Milvus (vector DB)
   │  └─ Return chunk IDs
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

## Service dependency map

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend    │────►│    Kong      │────►│  Keycloak    │
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

| Caller        | Callee                  | Purpose                                                                         | Method                |
| ------------- | ----------------------- | ------------------------------------------------------------------------------- | --------------------- |
| agent-service | user-service            | Permission checks, batched persona owner lookup, user lookup, and memories CRUD | HTTP + internal token |
| agent-service | rag-service             | RAG collections proxy                                                           | HTTP + internal token |
| agent-service | rag-service             | Agent knowledge availability checks for selected document and graph collections | HTTP + internal token |
| agent-service | tools-service           | MCP tool execution                                                              | HTTP + JWT            |
| agent-service | Airbyte                 | Datasource sync management                                                      | Airbyte API           |
| rag-service   | user-service            | Bearer-token identity resolution and permission checks                                                                | HTTP + forwarded JWT or internal token |
| tools-service | user-service            | Permission resolution                                                           | HTTP + internal token |
| rag-service   | Ollama/OpenAI           | LLM calls for graph extraction                                                  | HTTP (outbound)       |
| agent-service | Ollama/OpenAI/Anthropic | LLM inference                                                                   | HTTP (outbound)       |

---

## Internal vs external routing

### External (through Kong)

```
Browser → Kong:8000/agent-service/api/v1/*  → agent-service:8080
Browser → Kong:8000/user-service/api/v1/*   → user-service:8090
Browser → Kong:8000/rag-service/api/v1/*    → rag-service:8083
Browser → Kong:8000/tools-service/mcp       → tools-service:8003
```

### Internal (service-to-service)

```
Service → http://kong:8000/internal/user-service  → user-service:8090
Service → http://kong:8000/internal/rag-service   → rag-service:8083
Service → http://kong:8000/internal/tools-service/mcp → tools-service:8003
```

Internal calls use `X-Internal-Service-Token` header instead of JWT.

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
Service A has a Keycloak subject ID, needs the local user:
  GET /api/v1/internal/users/by-keycloak-id/{keycloak_id}
  Header: X-Internal-Service-Token
  ← Returns user dict with local user_id, email, role
```

Persona creation uses this identity resolution path before persistence. It stores
the returned local user ID when available and otherwise falls back to the
authenticated ID.

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

### Pattern 5: Organization-scoped access management

User-service is the policy authority for organization membership and direct
agent or collection grants. Enterprise administrators can manage the entire
tree; unit managers can manage their own unit and descendants, including
appointing or removing other unit managers in that scope.

The organization membership UI reads the same composite-role catalog as the
admin Users page and adds `unit_manager`, displayed as **Birim Yöneticisi**, as
a scoped management role.
User-service validates submitted catalog names against its role repository;
arbitrary client-supplied names are rejected. Catalog roles stored on a
membership remain organization metadata and do not elevate the actor's global
administrator status. Values such as `member` and `viewer` are accepted only
when they exist in the authoritative catalog.

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

The Organizations page owns the hierarchy, selection, membership data,
management capability, and existing mutation callbacks. The full-screen visual
designer reuses that state and those callbacks; it doesn't introduce separate
organization, membership, or resource-access workflows.

```text
Administrator opens the organization designer
  Browser GET /api/user-service/organizations/tree
    -> Next.js user-service proxy forwards GET /api/v1/organizations/tree
  Browser GET /api/user-service/organizations/layout
    -> Next.js user-service proxy forwards GET /api/v1/organizations/layout
    -> saved positions place known nodes
    -> deterministic positions place new nodes
    -> writable IDs control node dragging

Administrator selects a node
  Browser GET /api/user-service/organizations/{org_id}/management-capability
  Browser GET /api/user-service/organizations/{org_id}/users
  -> Details and Users reuse the page's existing mutation callbacks
  -> Access owns its scoped permission PUT through OrganizationAccessPanel
     at /api/user-service/permissions/organizations/{org_id}/targets/{type}/{id}/resources/{resource_type}
  -> a successful Access PUT asks the page to revalidate the hierarchy/counts

Administrator drags writable nodes
  -> only local canvas coordinates change
  Browser PUT /api/user-service/organizations/layout
    -> Next.js user-service proxy forwards PUT /api/v1/organizations/layout
    -> dirty coordinates are debounced and saved as one atomic batch

Administrator chooses Move to...
  Browser POST /api/user-service/organizations/{org_id}/move
    -> Next.js user-service proxy forwards POST /api/v1/organizations/{org_id}/move
    -> hierarchy changes only through this explicit action
```

Mutation controls remain disabled until the selected organization's capability
request completes. Read-only nodes stay selectable, and the actor can pan,
zoom, fit the view, and inspect the hierarchy without mutation access.
When the hierarchy is empty, the designer shows root creation only when the
authenticated permission set includes `org:create`, which is the same
permission enforced by the user-service create route.

Pointer drag completion and completed keyboard movement both add coordinates
to the same debounced layout batch. Pointer drag change events don't add
duplicate writes. The client retains dirty coordinates when a layout save
fails. **Retry** sends
the retained batch again. Closing flushes a pending debounce and waits for an
active save. If that save fails, the overlay stays open until the administrator
retries or chooses **Discard and close**. Closing preserves the selected
organization on the underlying page. Layout writes use last-write-wins
semantics across administrators.

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
