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
- Admin pages use server-side admin checks first, then load fine-grained route
  permissions in `UserProvider`. Permission fetch failures must not redirect an
  already-authenticated admin to `/error/403`; only completed permission checks
  that deny the route trigger the 403 page.
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

| Caller | Callee | Purpose | Method |
|--------|--------|---------|--------|
| agent-service | user-service | Permission check, user lookup, memories CRUD | HTTP + internal token |
| agent-service | rag-service | RAG collections proxy | HTTP + internal token |
| agent-service | rag-service | Agent knowledge availability checks for selected document and graph collections | HTTP + internal token |
| agent-service | tools-service | MCP tool execution | HTTP + JWT |
| agent-service | Airbyte | Datasource sync management | Airbyte API |
| rag-service | user-service | Permission check | HTTP + internal token |
| tools-service | user-service | Permission resolution | HTTP + internal token |
| rag-service | Ollama/OpenAI | LLM calls for graph extraction | HTTP (outbound) |
| agent-service | Ollama/OpenAI/Anthropic | LLM inference | HTTP (outbound) |

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

### Pattern 5: RAG proxy

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
