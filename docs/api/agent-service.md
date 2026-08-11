# Agent Service API

**Service:** AI agent orchestration built on LangGraph, FastAPI, and Streamlit.
**Base URL:** `http://kong:8000/agent-service` (via Kong gateway) or `http://agent-service:8080` (direct)
**Canonical API prefix:** `/api/v1`
**Auth:** JWT Bearer token (except `/api/v1/health` and `/api/v1/auth/health`). Internal calls use `X-Internal-Service-Token`.

Permissions are checked per-endpoint via `require_permission("<entity>:<action>")`.
Compatibility aliases may remain during migration. New integrations must use
the canonical `/api/v1` paths documented here.

---

## Health

| Method | Path                  | Auth   | Description                             |
| ------ | --------------------- | ------ | --------------------------------------- |
| GET    | `/api/v1/health`      | Public | Health check (includes Langfuse status) |
| GET    | `/api/v1/auth/health` | Public | Auth controller health check            |

---

## Auth

| Method | Path                               | Permission | Description                                                        |
| ------ | ---------------------------------- | ---------- | ------------------------------------------------------------------ |
| GET    | `/api/v1/auth/me`                  | user auth  | Get current user data from token                                   |
| GET    | `/api/v1/auth/settings`            | user auth  | Get user settings (auto_scroll, app status, deep_research_enabled) |
| GET    | `/api/v1/auth/enterprise-settings` | user auth  | Get enterprise settings (app name, custom logo)                    |
| GET    | `/api/v1/auth/health`              | public     | Health check `{"status": "ok"}`                                    |
| GET    | `/api/v1/admin/mcp/servers`        | user auth  | List MCP servers (built-in tools server)                           |

---

## Agents

**Prefix:** `/api/v1/agents`

| Method | Path                               | Permission       | Description                                           |
| ------ | ---------------------------------- | ---------------- | ----------------------------------------------------- |
| GET    | `/api/v1/agents/info`              | `agent:list`     | List all agents, models, default agent, default model |
| GET    | `/api/v1/agents/catalog`           | `persona:read`   | List lightweight product agent summaries              |
| GET    | `/api/v1/agents/{agent_id}`        | `persona:read`   | Get full product agent detail                         |
| GET    | `/api/v1/agents/catalog`           | `persona:read`   | List lightweight product agent summaries              |
| GET    | `/api/v1/agents/{agent_id}`        | `persona:read`   | Get full product agent detail                         |
| POST   | `/api/v1/agents/{agent_id}/invoke` | `agent:invoke`   | Invoke agent — non-streaming response                 |
| POST   | `/api/v1/agents/invoke`            | `agent:invoke`   | Invoke default agent — non-streaming                  |
| POST   | `/api/v1/agents/{agent_id}/stream` | `agent:stream`   | Stream agent response (SSE events)                    |
| POST   | `/api/v1/agents/stream`            | `agent:stream`   | Stream default agent response                         |
| POST   | `/api/v1/agents/feedback`          | `agent:feedback` | Submit run feedback                                   |
| POST   | `/api/v1/agents/history`           | `chat:read`      | Get chat history for a thread                         |

**Stream SSE events:** `token`, `message`, `reasoning_start`, `reasoning_delta`, `custom_tool_start`, `custom_tool_delta`, `custom_step_start`, `long_term_memory_recall`, `long_term_memory_save`, `error`, `[DONE]`

**Thinking tags:** Built-in `<thinking>` / `<think>` tag processing (DeepSeek, Qwen models) with streaming state machine.

---

## Agent Definitions

**Prefix:** `/api/v1/agent-definitions`

| Method | Path                                                         | Permission     | Description                                              |
| ------ | ------------------------------------------------------------ | -------------- | -------------------------------------------------------- |
| GET    | `/api/v1/agent-definitions/schemas/list`                     | `agent:list`   | List graph schemas with capabilities                     |
| GET    | `/api/v1/agent-definitions/brains/list`                      | `agent:list`   | List brain types                                         |
| GET    | `/api/v1/agent-definitions/memory/list`                      | `agent:list`   | List memory types                                        |
| POST   | `/api/v1/agent-definitions`                                  | `agent:create` | Create dynamic agent definition                          |
| GET    | `/api/v1/agent-definitions`                                  | `agent:list`   | List definitions (filter: `graph_schema`, `active_only`) |
| POST   | `/api/v1/agent-definitions/validate-composition`             | `agent:read`   | Validate sub-agent composition                           |
| POST   | `/api/v1/agent-definitions/available-for-composition`        | `agent:read`   | List agents available as sub-agents                      |
| GET    | `/api/v1/agent-definitions/{definition_id}/composition-info` | `agent:read`   | Get hierarchical composition for UI                      |
| PUT    | `/api/v1/agent-definitions/{definition_id}/sub-agents`       | `agent:update` | Update sub-agent references                              |
| GET    | `/api/v1/agent-definitions/{definition_id}`                  | `agent:read`   | Get definition by ID                                     |
| PUT    | `/api/v1/agent-definitions/{definition_id}`                  | `agent:update` | Update definition (partial)                              |
| DELETE | `/api/v1/agent-definitions/{definition_id}`                  | `agent:delete` | Delete definition                                        |

---

## Agent Groups

**Prefix:** `/api/v1/agent-groups`

| Method | Path                              | Permission     | Description              |
| ------ | --------------------------------- | -------------- | ------------------------ |
| GET    | `/api/v1/agent-groups`            | `agent:read`   | List agent access groups |
| POST   | `/api/v1/agent-groups`            | `agent:assign` | Create agent group       |
| PATCH  | `/api/v1/agent-groups/{group_id}` | `agent:assign` | Update agent group       |
| DELETE | `/api/v1/agent-groups/{group_id}` | `agent:assign` | Delete agent group       |

---

## Agent Tools

**Prefix:** `/api/v1/assistants`

| Method | Path                                            | Permission         | Description                 |
| ------ | ----------------------------------------------- | ------------------ | --------------------------- |
| GET    | `/api/v1/assistants/{agent_id}/tools`           | `mcp_tool:read`    | Get tools bound to an agent |
| POST   | `/api/v1/assistants/{agent_id}/tools`           | `assistant:update` | Add tools to agent (bulk)   |
| POST   | `/api/v1/assistants/{agent_id}/tools/{tool_id}` | `assistant:update` | Add single tool to agent    |
| DELETE | `/api/v1/assistants/{agent_id}/tools/{tool_id}` | `assistant:update` | Remove tool from agent      |
| PUT    | `/api/v1/assistants/{agent_id}/tools/reorder`   | `assistant:update` | Reorder agent tools         |

---

## Assistants

**Prefix:** `/api/v1/assistants`

| Method | Path                                | Permission         | Description                                  |
| ------ | ----------------------------------- | ------------------ | -------------------------------------------- |
| POST   | `/api/v1/assistants/search`         | `assistant:search` | Search assistants (LangGraph SDK compatible) |
| GET    | `/api/v1/assistants/{assistant_id}` | `assistant:read`   | Get assistant by ID                          |
| POST   | `/api/v1/assistants`                | `assistant:create` | Create assistant                             |
| PUT    | `/api/v1/assistants/{assistant_id}` | `assistant:update` | Update assistant (full)                      |
| PATCH  | `/api/v1/assistants/{assistant_id}` | `assistant:update` | Update assistant (partial)                   |
| DELETE | `/api/v1/assistants/{assistant_id}` | `assistant:delete` | Delete assistant                             |

---

## Assistant Schemas

| Method | Path                                        | Permission       | Description                               |
| ------ | ------------------------------------------- | ---------------- | ----------------------------------------- |
| GET    | `/api/v1/assistants/{assistant_id}/schemas` | `assistant:read` | Get graph config schemas with UI metadata |

---

## Chat

**Prefix:** `/api/v1/chat`

| Method      | Path                                                 | Permission    | Description                           |
| ----------- | ---------------------------------------------------- | ------------- | ------------------------------------- |
| GET         | `/api/v1/chat/get-user-chat-sessions`                | `chat:read`   | List user's chat sessions             |
| GET         | `/api/v1/chat/sessions`                              | `chat:read`   | REST alias for listing sessions       |
| POST        | `/api/v1/chat/create-chat-session`                   | `chat:send`   | Create chat session                   |
| POST        | `/api/v1/chat/sessions`                              | `chat:send`   | REST alias for creating a session     |
| GET         | `/api/v1/chat/get-chat-session/{session_id}`         | `chat:read`   | Get session with messages             |
| GET         | `/api/v1/chat/sessions/{session_id}`                 | `chat:read`   | REST alias for getting a session      |
| POST/DELETE | `/api/v1/chat/delete-chat-session/{session_id}`      | `chat:delete` | Delete chat session                   |
| DELETE      | `/api/v1/chat/sessions/{session_id}`                 | `chat:delete` | REST alias for deleting a session     |
| POST/DELETE | `/api/v1/chat/delete-all-chat-sessions`              | `chat:delete` | Delete all user sessions              |
| PUT/PATCH   | `/api/v1/chat/rename-chat-session`                   | `chat:send`   | Rename session                        |
| PUT         | `/api/v1/chat/update-chat-session-model`             | `chat:send`   | Update model override                 |
| PUT         | `/api/v1/chat/update-chat-session-temperature`       | `chat:send`   | Update temperature override           |
| POST        | `/api/v1/chat/stop-chat-session/{session_id}`        | `chat:send`   | Stop running session                  |
| POST        | `/api/v1/chat/send-chat-message`                     | `chat:send`   | Send message (streaming SSE response) |
| POST        | `/api/v1/chat/messages`                              | `chat:send`   | REST alias for sending a message      |
| POST        | `/api/v1/chat/create-chat-message-feedback`          | `chat:send`   | Create message feedback               |
| DELETE      | `/api/v1/chat/remove-chat-message-feedback`          | `chat:delete` | Remove message feedback               |
| GET         | `/api/v1/chat/available-context-tokens`              | `chat:read`   | Get available context tokens          |
| GET         | `/api/v1/chat/available-context-tokens/{session_id}` | `chat:read`   | Get context tokens for session        |

The `send-chat-message` endpoint handles: base64 file descriptors, LLM provider resolution (fetches provider API keys, base URLs), MinIO persistence, thread ownership checks.

Chat session list and detail responses include `time_created`, `time_updated`,
`last_message_at`, and `last_accessed_at`. Use `last_message_at` for
conversation activity ordering. If the field is present and `null`, the session
has no accepted user-message activity and orders by `time_created`. Use
`last_accessed_at` only for read telemetry; opening a chat must not move it in
Recents or project chat lists. The list endpoints accept `page_size`,
`before_activity`, and `before_id` for activity-keyset pagination and return
`next_cursor` with the same cursor field names when another page is available.

---

## Threads

**Prefix:** `/api/v1/threads`

| Method | Path                                | Permission      | Description                                               |
| ------ | ----------------------------------- | --------------- | --------------------------------------------------------- |
| POST   | `/api/v1/threads/search`            | `thread:search` | Search threads with state enrichment                      |
| POST   | `/api/v1/threads`                   | `thread:create` | Create thread                                             |
| GET    | `/api/v1/threads/{thread_id}`       | `thread:read`   | Get thread                                                |
| GET    | `/api/v1/threads/{thread_id}/state` | `thread:read`   | Get thread state with messages (LangGraph SDK compatible) |
| PATCH  | `/api/v1/threads/{thread_id}`       | `thread:update` | Update thread metadata                                    |
| DELETE | `/api/v1/threads/{thread_id}`       | `thread:delete` | Delete thread                                             |

---

## Runs

| Method | Path                                               | Permission   | Description                                                              |
| ------ | -------------------------------------------------- | ------------ | ------------------------------------------------------------------------ |
| POST   | `/api/v1/threads/{thread_id}/runs/stream`          | `run:create` | Stream runs for thread (SDK-compatible SSE). Resolves agent, config, LTM |
| POST   | `/api/v1/threads/{thread_id}/runs/{run_id}/cancel` | `run:cancel` | Cancel active run                                                        |
| POST   | `/api/v1/threads/{thread_id}/history`              | `run:read`   | Get thread history states                                                |

---

## Personas

New personas resolve and store the authoritative local user-service UUID as
their owner ID. If identity resolution has no primary ID, creation falls back to
the authenticated ID. Persona responses resolve the
current owner email from user-service. List requests resolve up to 100 distinct,
visible UUID owner IDs in one batch. Missing users, overflow owners, invalid
legacy IDs, and lookup failures return `Unknown user` without failing the persona
list. Legacy email-shaped owner IDs remain visible.

**Prefix:** `/api/v1/persona`

Personas can include `mcp_tools` and `mcp_tool_configs`. When a persona enables
the built-in `send_email` tool, `mcp_tool_configs.send_email.mail_config_id`
must reference an active mail config owned by the same user. Personas that don't
enable `send_email` don't need a mail config. When a user attaches files to the
current chat, agent-service passes those files to the mail tool as a
request-scoped `mail_attachments` runtime context. The agent sees only the file
names in its tool policy, and the service resolves the base64 attachment payload
server-side when `send_email` runs.

New frontend list views must prefer `/api/v1/agents/catalog`. The persona list
endpoint remains available for compatibility and returns the existing full
persona-shaped payload. Use `/api/v1/persona/{persona_id}` or
`/api/v1/agents/{agent_id}` when full detail is required.

| Method | Path                                 | Permission       | Description                       |
| ------ | ------------------------------------ | ---------------- | --------------------------------- |
| GET    | `/api/v1/persona`                    | `persona:read`   | List personas (built-in + custom) |
| GET    | `/api/v1/persona/options`            | `persona:read`   | List lightweight visible persona assignment options |
| GET    | `/api/v1/persona/labels`             | `persona:read`   | Get persona labels                |
| POST   | `/api/v1/persona`                    | `persona:create` | Create persona                    |
| GET    | `/api/v1/persona/{persona_id}`       | `persona:read`   | Get persona by ID                 |
| PATCH  | `/api/v1/persona/{persona_id}`       | `persona:update` | Update persona                    |
| DELETE | `/api/v1/persona/{persona_id}`       | `persona:delete` | Delete persona                    |
| POST   | `/api/v1/admin/persona/upload-image` | `persona:create` | Upload persona image (mock)       |

---

## Providers (LLM)

**Prefix:** `/api/v1/admin`

| Method | Path                                                | Permission        | Description                              |
| ------ | --------------------------------------------------- | ----------------- | ---------------------------------------- |
| GET    | `/api/v1/admin/providers`                           | `provider:read`   | List providers (builtin, url, user)      |
| GET    | `/api/v1/admin/providers/available-models`          | `provider:read`   | Get available models                     |
| POST   | `/api/v1/admin/providers`                           | `provider:create` | Create URL-based provider                |
| PUT    | `/api/v1/admin/providers/{provider_id}`             | `provider:update` | Update URL-based provider                |
| DELETE | `/api/v1/admin/providers/{provider_id}`             | `provider:delete` | Delete URL-based provider                |
| PUT    | `/api/v1/admin/providers/order`                     | `provider:update` | Reorder providers                        |
| PATCH  | `/api/v1/admin/providers/{config_id}/default-model` | `provider:update` | Update default model for provider config |
| POST   | `/api/v1/admin/user-providers`                      | `provider:create` | Create API-key-based user provider       |
| PUT    | `/api/v1/admin/user-providers/{provider_id}`        | `provider:update` | Update user provider                     |
| DELETE | `/api/v1/admin/user-providers/{provider_id}`        | `provider:delete` | Delete user provider                     |
| GET    | `/api/v1/admin/providers/well-known`                | user auth         | Get well-known provider catalog          |
| POST   | `/api/v1/admin/providers/test-connection`           | `provider:read`   | Test provider connection                 |
| GET    | `/api/v1/admin/providers/{provider_id}/models`      | `provider:read`   | Get provider models                      |
| POST   | `/api/v1/admin/providers/{provider_id}/sync-models` | `provider:update` | Sync provider models                     |
| POST   | `/api/v1/admin/ollama/pull`                         | `provider:update` | Pull Ollama model (streaming SSE)        |
| GET    | `/api/v1/admin/vllm/models`                         | `provider:read`   | Get vLLM models                          |

---

## Datasources

**Prefix:** `/api/v1/datasources`

| Method | Path                                             | Permission          | Description                                                   |
| ------ | ------------------------------------------------ | ------------------- | ------------------------------------------------------------- |
| GET    | `/api/v1/datasources/connectors`                 | user auth           | List Airbyte source connectors (filter: `category`, `search`) |
| GET    | `/api/v1/datasources/connectors/{name}/spec`     | user auth           | Get connector JSON Schema config spec                         |
| POST   | `/api/v1/datasources/connectors/{name}/validate` | user auth           | Validate connector config                                     |
| POST   | `/api/v1/datasources/connectors/{name}/streams`  | user auth           | Get available streams for connector                           |
| GET    | `/api/v1/datasources`                            | user auth           | List configured datasources                                   |
| POST   | `/api/v1/datasources`                            | `datasource:create` | Create datasource (Airbyte source + connection + destination) |
| GET    | `/api/v1/datasources/{id}/details`               | user auth           | Get datasource details with paginated chunks                  |
| PUT    | `/api/v1/datasources/{id}`                       | `datasource:update` | Update datasource                                             |
| POST   | `/api/v1/datasources/{id}/sync`                  | `datasource:sync`   | Trigger sync                                                  |
| GET    | `/api/v1/datasources/{id}/status`                | user auth           | Get sync status                                               |
| GET    | `/api/v1/datasources/{id}/sync-history`          | user auth           | Get sync job history                                          |
| DELETE | `/api/v1/datasources/{id}`                       | `datasource:delete` | Delete datasource                                             |

---

## Sync Schedules

**Prefix:** `/api/v1/datasources`

| Method | Path                                       | Permission        | Description                                       |
| ------ | ------------------------------------------ | ----------------- | ------------------------------------------------- |
| GET    | `/api/v1/datasources/schedules`            | user auth         | List all sync schedules                           |
| POST   | `/api/v1/datasources/{id}/schedule`        | `schedule:create` | Create sync schedule (cron on Airbyte connection) |
| GET    | `/api/v1/datasources/{id}/schedule`        | user auth         | Get schedule for datasource                       |
| PUT    | `/api/v1/datasources/{id}/schedule`        | `schedule:update` | Update schedule                                   |
| DELETE | `/api/v1/datasources/{id}/schedule`        | `schedule:delete` | Delete schedule (set to manual)                   |
| GET    | `/api/v1/datasources/{id}/schedule/status` | user auth         | Get combined sync + schedule status               |

---

## Ingestion

| Method | Path                     | Auth            | Description                                                                      |
| ------ | ------------------------ | --------------- | -------------------------------------------------------------------------------- |
| POST   | `/api/v1/batch`          | User / Internal | Ingest batch of records → documents → chunks → embed → vector DB. Zero disk I/O. |
| POST   | `/api/v1/source-preview` | User / Internal | Fetch sample records from Airbyte source for preview                             |

---

## MCP Providers

**Prefix:** `/api/v1/mcp-providers`

| Method | Path                                       | Permission            | Description              |
| ------ | ------------------------------------------ | --------------------- | ------------------------ |
| GET    | `/api/v1/mcp-providers`                    | `mcp_provider:read`   | List MCP providers       |
| GET    | `/api/v1/mcp-providers/{provider_id}`      | `mcp_provider:read`   | Get provider by ID       |
| POST   | `/api/v1/mcp-providers`                    | `mcp_provider:create` | Create MCP provider      |
| POST   | `/api/v1/mcp-providers/{provider_id}/sync` | `mcp_provider:sync`   | Sync tools from provider |
| PATCH  | `/api/v1/mcp-providers/{provider_id}`      | `mcp_provider:update` | Update provider          |
| DELETE | `/api/v1/mcp-providers/{provider_id}`      | `mcp_provider:delete` | Delete provider          |

---

## MCP Tools

**Prefix:** `/api/v1/mcp-tools`

| Method | Path                                            | Permission      | Description                          |
| ------ | ----------------------------------------------- | --------------- | ------------------------------------ |
| GET    | `/api/v1/mcp-tools`                             | `mcp_tool:read` | List MCP tools                       |
| GET    | `/api/v1/mcp-tools/available`                   | `mcp_tool:read` | List available tools with categories |
| GET    | `/api/v1/mcp-tools/categories`                  | `mcp_tool:read` | List tool categories                 |
| GET    | `/api/v1/mcp-tools/categories/{category}`       | `mcp_tool:read` | Get tools by category                |
| GET    | `/api/v1/mcp-tools/{tool_id}`                   | `mcp_tool:read` | Get tool by ID                       |
| GET    | `/api/v1/mcp-tools/provider/{provider_id}`      | `mcp_tool:read` | List tools by provider               |
| POST   | `/api/v1/mcp-tools/sync`                        | `mcp_tool:sync` | Sync all tools from all providers    |
| POST   | `/api/v1/mcp-tools/provider/{provider_id}/sync` | `mcp_tool:sync` | Sync tools from specific provider    |
| DELETE | `/api/v1/mcp-tools/{tool_id}`                   | `mcp_tool:sync` | Delete tool                          |

---

## Mail configs

**Prefix:** `/api/v1/mail-configs`

Mail configs store SMTP account settings for agent-owned email sending.
Responses never include SMTP passwords. The service stores encrypted secrets
and only resolves them at runtime when an agent calls `send_email`.

| Method | Path                                    | Auth      | Description                                                           |
| ------ | --------------------------------------- | --------- | --------------------------------------------------------------------- |
| GET    | `/api/v1/mail-configs`                  | user auth | List active SMTP mail configs for the current user                    |
| POST   | `/api/v1/mail-configs`                  | user auth | Create an SMTP mail config with encrypted password storage            |
| GET    | `/api/v1/mail-configs/{config_id}`      | user auth | Get a masked mail config by ID                                        |
| PATCH  | `/api/v1/mail-configs/{config_id}`      | user auth | Update an SMTP mail config; omit `password` to keep the stored secret |
| DELETE | `/api/v1/mail-configs/{config_id}`      | user auth | Deactivate a mail config                                              |
| POST   | `/api/v1/mail-configs/{config_id}/test` | user auth | Send a test email through the selected SMTP config                    |
| POST   | `/api/v1/mail-configs/{config_id}/send` | user auth | Send an email through the selected SMTP config                        |

`POST /api/v1/mail-configs/{config_id}/send` accepts the same safe email
payload used by the playground: `to`, `subject`, `body`, optional `cc`, `bcc`,
`is_html`, `reply_to`, and optional `attachments`. Each attachment object must
include `filename`, `mime_type`, and `content_base64`.

---

## Proxy

**Prefix:** `/api/v1/proxy`

| Method | Path                              | Auth      | Description                            |
| ------ | --------------------------------- | --------- | -------------------------------------- |
| GET    | `/api/v1/proxy/mcp/tools`         | user auth | List MCP tools from a server URL       |
| GET    | `/api/v1/proxy/ollama/models`     | user auth | List Ollama models                     |
| GET    | `/api/v1/proxy/rag/collections`   | user auth | Proxy to RAG collections               |
| GET    | `/api/v1/proxy/mcp/tools-builtin` | user auth | List tools from built-in tools-service |
| POST   | `/api/v1/proxy/mcp/execute`       | user auth | Execute MCP tool                       |

---

## Web Search

**Prefix:** `/api/v1/admin/web-search`

| Method | Path                                                         | Auth      | Description                    |
| ------ | ------------------------------------------------------------ | --------- | ------------------------------ |
| GET    | `/api/v1/admin/web-search/search-providers`                  | user auth | List search providers          |
| GET    | `/api/v1/admin/web-search/content-providers`                 | user auth | List content providers         |
| POST   | `/api/v1/admin/web-search/content-providers/test`            | user auth | Test content provider          |
| POST   | `/api/v1/admin/web-search/content-providers/crawl`           | user auth | Crawl a URL                    |
| POST   | `/api/v1/admin/web-search/content-providers/reset-default`   | user auth | Reset default content provider |
| POST   | `/api/v1/admin/web-search/content-providers/{id}/activate`   | user auth | Activate content provider      |
| POST   | `/api/v1/admin/web-search/content-providers/{id}/deactivate` | user auth | Deactivate content provider    |

---

## Files

| Method | Path                               | Auth      | Description                                                           |
| ------ | ---------------------------------- | --------- | --------------------------------------------------------------------- |
| GET    | `/api/v1/chat/file/{file_id}`      | user auth | Serve file bytes (XLSX as CSV). In-memory cache, falls back to MinIO. |
| GET    | `/api/v1/chat/file/{file_id}?download=1` | user auth | Same file, forced `Content-Disposition: attachment` with original bytes/filename (no XLSX-to-CSV conversion). Used for agent-generated document downloads. |
| GET    | `/api/v1/chat/file/{file_id}/text` | user auth | Extract plain text from document (docx, pdf, pptx)                    |

---

## Document output tools

Two LangChain tools — `create_document` (PDF/DOCX/MD/TXT from a restricted
Markdown subset) and `create_spreadsheet` (XLSX/CSV from tabular rows) — are
injected into every agent graph built by `GraphBuilder`
(`agents/graphs/builder.py`), `ConfigurableMCPAgent`, and the default
`chatbot` graph. They are **not** opt-in MCP tools configured per agent; they
are always present unless `DOCUMENT_TOOLS_ENABLED=false` (see
`core/settings.py`).

- Rendering: `service/DocumentGenerationService.py` (pure, no I/O). PDF
  Unicode text (Turkish characters) requires the `DejaVuSans` TTF font,
  installed via `fonts-dejavu-core` in `docker/Dockerfile.service`; without it
  PDFs silently fall back to Helvetica (ASCII only).
- Persistence: `agents/document_tools.py` stores bytes in the in-memory
  `FileService` cache, uploads to MinIO (`service/MinioService.py`), and
  writes a `document` row scoped to the current `thread_id`/`user_id` — the
  same table and MinIO bucket layout used for user-uploaded chat files. Both
  MinIO and DB writes are best-effort: a failure there is logged and the file
  is still served for the current session, since `FileService` already has
  it.
- The default `chatbot` graph (`agents/chatbot.py`) is otherwise a single
  `model.ainvoke()` call with no tool loop. `_run_with_document_tools`
  attempts `model.bind_tools(...)`; if the model doesn't support tool
  binding, it silently falls back to the original plain-call behavior — no
  crash, no tools available for that model.
- Bad tool calls: models regularly call `create_document` without the required
  `content` (or with the body under an invented key), which makes LangChain
  raise a pydantic `ValidationError` from `tool.ainvoke`. In this hand-rolled
  loop that exception used to escape the graph node and kill the SSE stream
  mid-answer. `_run_tool_call` now mirrors LangGraph's prebuilt `ToolNode`:
  the failure comes back as the tool's `ToolMessage` content, naming the
  missing or invalid arguments, so the next loop iteration can correct itself.
  React-based agents already got this from `ToolNode`. Before validation runs,
  `recover_document_tool_args` repairs the two shapes local models produce most
  often — the body under an alias key (`text`, `body`, `markdown`, …) or inlined
  as `<content>…</content>` inside an unrelated argument — because rejecting
  those costs the user a full regeneration of a long document. It only ever
  *adds* `content`; a description-shaped argument is never promoted to the body,
  so genuinely wrong calls still fail loudly. Two related guards:
  a tool call without an `id` gets a synthetic one rather than raising, and if
  the loop exhausts `_MAX_DOCUMENT_TOOL_ITERATIONS` while the model is still
  calling tools, one final **unbound** `model.ainvoke` produces a plain text
  answer — otherwise the reply would be a raw tool result with no assistant
  text. On the client, a failed attempt keeps its timeline turn pinned
  (`lib/search/streamingUtils.ts`) and a fresh `document_generation_start`
  clears the previous outcome, so a successful retry replaces the failure
  notice instead of stacking underneath it.
- Wire format: each tool call returns a JSON string as its `ToolMessage`
  content, shaped `{"__generated_file__": true, "file_id", "filename",
  "mime_type", "size_bytes", "download_url"}`. Both the live SSE path
  (`AgentsRoute.message_generator`) and the chat-history rebuild path
  (`controller/chat_controller.py`) recognize this via the shared
  `service/GeneratedFilePacket.py` helpers and emit a `generated_file` SSE
  packet (`type: "generated_file"`). Neither path emits the generic
  `custom_tool_start` / `custom_tool_delta` timeline packets for these two
  tools — the file card and the progress packets below replace them, so live
  streaming and a page refresh render the same thing. The frontend renders the
  card inline in the message body (`GeneratedFileRenderer.tsx`), not inside the
  collapsible tool timeline. Clicking the card opens the same shared
  file-preview modal used for uploaded chat files
  (`sections/modals/TextViewModal.tsx`, keyed by `file_id`) rather than
  downloading directly — the modal has its own download action. The
  `?download=1` variant exists for callers that need a forced attachment
  response directly.
- Progress: the model writes the whole document body into the tool call's
  `content` argument, which `remove_tool_calls()` strips — so for the entire
  time the document is being written the stream emits nothing and looks frozen.
  `service/DocumentProgressTracker.py` watches the streamed `tool_call_chunks`
  and turns that silence into three packets:

  | Packet | Emitted when | Payload |
  | ------ | ------------ | ------- |
  | `document_generation_start` | first argument chunk of a document tool call | `tool_name`, `filename`, `format`, `phase` |
  | `document_generation_progress` | every ~300 argument characters, and once when rendering begins | as above plus `chars` |
  | `document_generation_end` | tool result arrives (or the stream dies) | as above plus `status` (`success` / `error` / `incomplete`), `error` |

  `filename` and `format` are recovered from the partially streamed JSON
  arguments, so they are usually known long before the file exists; both are
  `null` until then. `phase` moves from `"writing"` to `"rendering"` when the
  arguments are complete and the tool starts producing bytes. Every `start` is
  followed by exactly one `end` — the generator flushes an in-flight generation
  in its `finally` block so a dropped stream cannot leave the UI waiting
  forever. These packets share a timeline turn with the `generated_file` packet
  (`lib/search/packetCategories.ts`), so the frontend skeleton
  (`DocumentGenerationSkeleton.tsx`) is replaced in place by the file card.
  Unlike every other tool packet, they do **not** advance the turn index in
  `lib/search/streamingUtils.ts`: a model often begins its tool call mid-word,
  and treating that as a turn boundary cut the reply in half around the card.
  They ride the answer's turn and are kept apart by the category's `genfile`
  group suffix, which is why `GroupedPacket` carries an explicit `key` — two
  display groups can now share one turn_index/tab_index pair.
  History rebuilds emit no progress packets: nothing is being generated on a
  refresh, so the card is rendered directly.
- Live tool packets: a node's `updates` only reach the stream once the whole
  node returns, and the default `chatbot` graph runs its entire tool loop inside
  one `call_model` node. `agents/document_tools.py` therefore publishes the
  rendering-phase progress packet, the `generated_file` packet and the closing
  `document_generation_end` through LangGraph's `get_stream_writer()` (custom
  stream mode) as soon as the file exists, instead of waiting for the node.
  `message_generator` de-duplicates by `file_id` and calls
  `DocumentProgressTracker.close()` so the same file is never announced twice
  when the `ToolMessage` shows up at node end; the tracker also ignores a tool
  call id it has already finished. Emitting is best-effort — outside a graph
  runtime `get_stream_writer()` raises and the ToolMessage path still covers it.
- Token streaming across an in-node tool loop: `message_generator` filters
  tokens by the first LLM call's message id so background calls (memory
  extraction) stay out of the answer. That id is normally reset by the `updates`
  event for a tool call — which never arrives in time when the tool loop lives
  inside one node, so the entire post-tool answer used to be dropped and then
  delivered as a single `message` packet with no streaming animation. The filter
  now also advances when the current call produced `tool_call_chunks` (a call
  that made tool calls is always followed by an answer call), and the final
  `message` packet is suppressed for any message id whose tokens already
  streamed. Memory extraction is tagged `skip_stream` (`memory/long_term.py`)
  so it is filtered by tag rather than by id heuristics.

---

## User / Projects

| Method | Path                                                   | Permission       | Description                           |
| ------ | ------------------------------------------------------ | ---------------- | ------------------------------------- |
| GET    | `/api/v1/user/files/recent`                            | `project:read`   | Get recent files                      |
| GET    | `/api/v1/llm/persona/{persona_id}/providers`           | `provider:read`  | Get persona LLM providers             |
| GET    | `/api/v1/llm/provider`                                 | `provider:read`  | Get LLM provider config               |
| GET    | `/api/v1/admin/llm/built-in/options`                   | `provider:read`  | Get built-in LLM options              |
| POST   | `/api/v1/admin/llm/test/default`                       | `provider:read`  | Test default LLM                      |
| GET    | `/api/v1/user/projects`                                | `project:read`   | Get user projects with chat sessions  |
| POST   | `/api/v1/user/projects/create`                         | `project:create` | Create project                        |
| POST   | `/api/v1/user/projects/file/upload`                    | `project:update` | Upload files (multipart)              |
| GET    | `/api/v1/user/projects/files/{project_id}`             | `project:read`   | Get project files                     |
| POST   | `/api/v1/user/projects/{project_id}/files/{file_id}`   | `project:update` | Link file to project                  |
| DELETE | `/api/v1/user/projects/{project_id}/files/{file_id}`   | `project:update` | Unlink file from project              |
| GET    | `/api/v1/user/projects/file/{file_id}`                 | `project:read`   | Get user file                         |
| DELETE | `/api/v1/user/projects/file/{file_id}`                 | `project:delete` | Delete file                           |
| POST   | `/api/v1/user/projects/file/statuses`                  | `project:read`   | Get file statuses                     |
| GET    | `/api/v1/user/projects/{project_id}`                   | `project:read`   | Get project with sessions             |
| PATCH  | `/api/v1/user/projects/{project_id}`                   | `project:update` | Rename project                        |
| DELETE | `/api/v1/user/projects/{project_id}`                   | `project:delete` | Delete project                        |
| GET    | `/api/v1/user/projects/{project_id}/details`           | `project:read`   | Get project details (files, personas) |
| GET    | `/api/v1/user/projects/{project_id}/instructions`      | `project:read`   | Get project instructions              |
| POST   | `/api/v1/user/projects/{project_id}/instructions`      | `project:update` | Upsert project instructions           |
| GET    | `/api/v1/user/projects/{project_id}/token-count`       | `project:read`   | Get token count                       |
| POST   | `/api/v1/user/projects/{project_id}/move_chat_session` | `project:update` | Move session to project               |
| POST   | `/api/v1/user/projects/remove_chat_session`            | `project:update` | Remove session from project           |

Project responses embed chat sessions with the same timestamp fields as the
chat session list. Project chat ordering follows `last_message_at` activity,
not `last_accessed_at` or read-time metadata updates.

---

## Session context helpers

| Method | Path                                                     | Permission  | Description             |
| ------ | -------------------------------------------------------- | ----------- | ----------------------- |
| GET    | `/api/v1/user/projects/session/{session_id}/token-count` | `chat:read` | Get session token count |
| GET    | `/api/v1/user/projects/session/{session_id}/files`       | `chat:read` | Get session files       |

---

## Admin LLM

| Method | Path                                         | Permission        | Description                   |
| ------ | -------------------------------------------- | ----------------- | ----------------------------- |
| GET    | `/api/v1/admin/llm/provider`                 | `provider:read`   | Get admin LLM provider config |
| POST   | `/api/v1/admin/llm/test`                     | `provider:read`   | Test LLM                      |
| POST   | `/api/v1/admin/llm/default`                  | `provider:update` | Set default LLM               |
| GET    | `/api/v1/admin/llm/ollama/available-models`  | `provider:read`   | List available Ollama models  |
| PUT    | `/api/v1/admin/llm/provider`                 | `provider:update` | Save LLM provider             |
| POST   | `/api/v1/admin/llm/provider`                 | `provider:create` | Create LLM provider           |
| GET    | `/api/v1/llm/persona/{persona_id}/providers` | `provider:read`   | Get persona providers         |

---

## Permission reference

| Permission                                                                                                    | Used by              |
| ------------------------------------------------------------------------------------------------------------- | -------------------- |
| `agent:assign`                                                                                                | Agent Groups         |
| `agent:create`, `agent:delete`, `agent:list`, `agent:read`, `agent:update`                                    | Agent Definitions    |
| `agent:feedback`                                                                                              | Agents feedback      |
| `agent:invoke`, `agent:stream`                                                                                | Agents invoke/stream |
| `assistant:create`, `assistant:delete`, `assistant:read`, `assistant:search`, `assistant:update`              | Assistants           |
| `chat:delete`, `chat:read`, `chat:send`                                                                       | Chat                 |
| `datasource:create`, `datasource:delete`, `datasource:sync`, `datasource:update`                              | Datasources          |
| `mcp_provider:create`, `mcp_provider:delete`, `mcp_provider:read`, `mcp_provider:sync`, `mcp_provider:update` | MCP Providers        |
| `mcp_tool:read`, `mcp_tool:sync`                                                                              | MCP Tools            |
| `persona:create`, `persona:delete`, `persona:read`, `persona:update`                                          | Personas             |
| `project:create`, `project:delete`, `project:read`, `project:update`                                          | User/Projects        |
| `provider:create`, `provider:delete`, `provider:read`, `provider:update`                                      | Providers            |
| `run:cancel`, `run:create`, `run:read`                                                                        | Runs                 |
| `schedule:create`, `schedule:delete`, `schedule:update`                                                       | Sync Schedules       |
| `thread:create`, `thread:delete`, `thread:read`, `thread:search`, `thread:update`                             | Threads              |
