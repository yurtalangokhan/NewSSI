# Agent Service API

**Service:** AI agent orchestration built on LangGraph, FastAPI, and Streamlit.
**Base URL:** `http://kong:8000/agent-service` (via Kong gateway) or `http://agent-service:8080` (direct)
**Canonical API prefix:** `/api/v1`
**Auth:** JWT Bearer token (except `/api/v1/health` and `/api/v1/auth/health`). Internal calls use `X-Internal-Service-Token`.

Permissions are checked per-endpoint via `require_permission("<entity>:<action>")`.
Legacy root and `/api/*` paths remain compatibility aliases during the
migration.

---

## Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/health` | Public | Health check (includes Langfuse status) |
| GET | `/api/v1/auth/health` | Public | Auth controller health check |

---

## Auth

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/me` | user auth | Get current user data from token |
| GET | `/settings` | user auth | Get user settings (auto_scroll, app status, deep_research_enabled) |
| GET | `/enterprise-settings` | user auth | Get enterprise settings (app name, custom logo) |
| GET | `/api/v1/auth/health` | public | Health check `{"status": "ok"}` |
| GET | `/api/admin/mcp/servers` | user auth | List MCP servers (built-in tools server) |

---

## Agents

**Prefix:** `/agents`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/agents/info` | `agent:list` | List all agents, models, default agent, default model |
| POST | `/agents/{agent_id}/invoke` | `agent:invoke` | Invoke agent — non-streaming response |
| POST | `/agents/invoke` | `agent:invoke` | Invoke default agent — non-streaming |
| POST | `/agents/{agent_id}/stream` | `agent:stream` | Stream agent response (SSE events) |
| POST | `/agents/stream` | `agent:stream` | Stream default agent response |
| POST | `/agents/feedback` | `agent:feedback` | Submit run feedback |
| POST | `/agents/history` | `chat:read` | Get chat history for a thread |

**Stream SSE events:** `token`, `message`, `reasoning_start`, `reasoning_delta`, `custom_tool_start`, `custom_tool_delta`, `custom_step_start`, `long_term_memory_recall`, `long_term_memory_save`, `error`, `[DONE]`

**Thinking tags:** Built-in `<thinking>` / `<think>` tag processing (DeepSeek, Qwen models) with streaming state machine.

---

## Agent Definitions

**Prefix:** `/agent-definitions`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/agent-definitions/schemas/list` | `agent:list` | List graph schemas with capabilities |
| GET | `/agent-definitions/brains/list` | `agent:list` | List brain types |
| GET | `/agent-definitions/memory/list` | `agent:list` | List memory types |
| POST | `/agent-definitions` | `agent:create` | Create dynamic agent definition |
| GET | `/agent-definitions` | `agent:list` | List definitions (filter: `graph_schema`, `active_only`) |
| POST | `/agent-definitions/validate-composition` | `agent:read` | Validate sub-agent composition |
| POST | `/agent-definitions/available-for-composition` | `agent:read` | List agents available as sub-agents |
| GET | `/agent-definitions/{definition_id}/composition-info` | `agent:read` | Get hierarchical composition for UI |
| PUT | `/agent-definitions/{definition_id}/sub-agents` | `agent:update` | Update sub-agent references |
| GET | `/agent-definitions/{definition_id}` | `agent:read` | Get definition by ID |
| PUT | `/agent-definitions/{definition_id}` | `agent:update` | Update definition (partial) |
| DELETE | `/agent-definitions/{definition_id}` | `agent:delete` | Delete definition |

---

## Agent Groups

**Prefix:** `/api/agent-groups`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/agent-groups` | `agent:read` | List agent access groups |
| POST | `/api/agent-groups` | `agent:assign` | Create agent group |
| PATCH | `/api/agent-groups/{group_id}` | `agent:assign` | Update agent group |
| DELETE | `/api/agent-groups/{group_id}` | `agent:assign` | Delete agent group |

---

## Agent Tools

**Prefix:** `/assistants`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/assistants/{agent_id}/tools` | `mcp_tool:read` | Get tools bound to an agent |
| POST | `/assistants/{agent_id}/tools` | `assistant:update` | Add tools to agent (bulk) |
| POST | `/assistants/{agent_id}/tools/{tool_id}` | `assistant:update` | Add single tool to agent |
| DELETE | `/assistants/{agent_id}/tools/{tool_id}` | `assistant:update` | Remove tool from agent |
| PUT | `/assistants/{agent_id}/tools/reorder` | `assistant:update` | Reorder agent tools |

---

## Assistants

**Prefix:** `/assistants`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/assistants/search` | `assistant:search` | Search assistants (LangGraph SDK compatible) |
| GET | `/assistants/{assistant_id}` | `assistant:read` | Get assistant by ID |
| POST | `/assistants` | `assistant:create` | Create assistant |
| PUT | `/assistants/{assistant_id}` | `assistant:update` | Update assistant (full) |
| PATCH | `/assistants/{assistant_id}` | `assistant:update` | Update assistant (partial) |
| DELETE | `/assistants/{assistant_id}` | `assistant:delete` | Delete assistant |

---

## Assistant Schemas

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/assistants/{assistant_id}/schemas` | `assistant:read` | Get graph config schemas with UI metadata |

---

## Chat

**Prefix:** `/api/chat`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/chat/get-user-chat-sessions` | `chat:read` | List user's chat sessions |
| POST | `/api/chat/create-chat-session` | `chat:send` | Create chat session |
| GET | `/api/chat/get-chat-session/{session_id}` | `chat:read` | Get session with messages |
| POST/DELETE | `/api/chat/delete-chat-session/{session_id}` | `chat:delete` | Delete chat session |
| POST/DELETE | `/api/chat/delete-all-chat-sessions` | `chat:delete` | Delete all user sessions |
| PUT/PATCH | `/api/chat/rename-chat-session` | `chat:send` | Rename session |
| PUT | `/api/chat/update-chat-session-model` | `chat:send` | Update model override |
| PUT | `/api/chat/update-chat-session-temperature` | `chat:send` | Update temperature override |
| POST | `/api/chat/stop-chat-session/{session_id}` | `chat:send` | Stop running session |
| POST | `/api/chat/send-chat-message` | `chat:send` | Send message (streaming SSE response) |
| POST | `/api/chat/create-chat-message-feedback` | `chat:send` | Create message feedback |
| DELETE | `/api/chat/remove-chat-message-feedback` | `chat:delete` | Remove message feedback |
| GET | `/api/chat/available-context-tokens` | `chat:read` | Get available context tokens |
| GET | `/api/chat/available-context-tokens/{session_id}` | `chat:read` | Get context tokens for session |

The `send-chat-message` endpoint handles: base64 file descriptors, LLM provider resolution (fetches provider API keys, base URLs), MinIO persistence, thread ownership checks.

---

## Threads

**Prefix:** `/threads`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/threads/search` | `thread:search` | Search threads with state enrichment |
| POST | `/threads` | `thread:create` | Create thread |
| GET | `/threads/{thread_id}` | `thread:read` | Get thread |
| GET | `/threads/{thread_id}/state` | `thread:read` | Get thread state with messages (LangGraph SDK compatible) |
| PATCH | `/threads/{thread_id}` | `thread:update` | Update thread metadata |
| DELETE | `/threads/{thread_id}` | `thread:delete` | Delete thread |

---

## Runs

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/threads/{thread_id}/runs/stream` | `run:create` | Stream runs for thread (SDK-compatible SSE). Resolves agent, config, LTM |
| POST | `/threads/{thread_id}/runs/{run_id}/cancel` | `run:cancel` | Cancel active run |
| POST | `/threads/{thread_id}/history` | `run:read` | Get thread history states |

---

## Personas

**Prefix:** `/api/persona`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/persona` | `persona:read` | List personas (built-in + custom) |
| GET | `/api/persona/labels` | `persona:read` | Get persona labels |
| POST | `/api/persona` | `persona:create` | Create persona |
| GET | `/api/persona/{persona_id}` | `persona:read` | Get persona by ID |
| PATCH | `/api/persona/{persona_id}` | `persona:update` | Update persona |
| DELETE | `/api/persona/{persona_id}` | `persona:delete` | Delete persona |
| POST | `/api/admin/persona/upload-image` | `persona:create` | Upload persona image (mock) |

---

## Providers (LLM)

**Prefix:** `/api/admin`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/admin/providers` | `provider:read` | List providers (builtin, url, user) |
| GET | `/api/admin/providers/available-models` | `provider:read` | Get available models |
| POST | `/api/admin/providers` | `provider:create` | Create URL-based provider |
| PUT | `/api/admin/providers/{provider_id}` | `provider:update` | Update URL-based provider |
| DELETE | `/api/admin/providers/{provider_id}` | `provider:delete` | Delete URL-based provider |
| PUT | `/api/admin/providers/order` | `provider:update` | Reorder providers |
| PATCH | `/api/admin/providers/{config_id}/default-model` | `provider:update` | Update default model for provider config |
| POST | `/api/admin/user-providers` | `provider:create` | Create API-key-based user provider |
| PUT | `/api/admin/user-providers/{provider_id}` | `provider:update` | Update user provider |
| DELETE | `/api/admin/user-providers/{provider_id}` | `provider:delete` | Delete user provider |
| GET | `/api/admin/providers/well-known` | user auth | Get well-known provider catalog |
| POST | `/api/admin/providers/test-connection` | `provider:read` | Test provider connection |
| GET | `/api/admin/providers/{provider_id}/models` | `provider:read` | Get provider models |
| POST | `/api/admin/providers/{provider_id}/sync-models` | `provider:update` | Sync provider models |
| POST | `/api/admin/ollama/pull` | `provider:update` | Pull Ollama model (streaming SSE) |
| GET | `/api/admin/vllm/models` | `provider:read` | Get vLLM models |

---

## Datasources

**Prefix:** `/datasources`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/datasources/connectors` | user auth | List Airbyte source connectors (filter: `category`, `search`) |
| GET | `/datasources/connectors/{name}/spec` | user auth | Get connector JSON Schema config spec |
| POST | `/datasources/connectors/{name}/validate` | user auth | Validate connector config |
| POST | `/datasources/connectors/{name}/streams` | user auth | Get available streams for connector |
| GET | `/datasources` | user auth | List configured datasources |
| POST | `/datasources` | `datasource:create` | Create datasource (Airbyte source + connection + destination) |
| GET | `/datasources/{id}/details` | user auth | Get datasource details with paginated chunks |
| PUT | `/datasources/{id}` | `datasource:update` | Update datasource |
| POST | `/datasources/{id}/sync` | `datasource:sync` | Trigger sync |
| GET | `/datasources/{id}/status` | user auth | Get sync status |
| GET | `/datasources/{id}/sync-history` | user auth | Get sync job history |
| DELETE | `/datasources/{id}` | `datasource:delete` | Delete datasource |

---

## Sync Schedules

**Prefix:** `/datasources`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/datasources/schedules` | user auth | List all sync schedules |
| POST | `/datasources/{id}/schedule` | `schedule:create` | Create sync schedule (cron on Airbyte connection) |
| GET | `/datasources/{id}/schedule` | user auth | Get schedule for datasource |
| PUT | `/datasources/{id}/schedule` | `schedule:update` | Update schedule |
| DELETE | `/datasources/{id}/schedule` | `schedule:delete` | Delete schedule (set to manual) |
| GET | `/datasources/{id}/schedule/status` | user auth | Get combined sync + schedule status |

---

## Ingestion

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/batch` | User / Internal | Ingest batch of records → documents → chunks → embed → vector DB. Zero disk I/O. |
| POST | `/source-preview` | User / Internal | Fetch sample records from Airbyte source for preview |

---

## MCP Providers

**Prefix:** `/mcp-providers`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/mcp-providers` | `mcp_provider:read` | List MCP providers |
| GET | `/mcp-providers/{provider_id}` | `mcp_provider:read` | Get provider by ID |
| POST | `/mcp-providers` | `mcp_provider:create` | Create MCP provider |
| POST | `/mcp-providers/{provider_id}/sync` | `mcp_provider:sync` | Sync tools from provider |
| PATCH | `/mcp-providers/{provider_id}` | `mcp_provider:update` | Update provider |
| DELETE | `/mcp-providers/{provider_id}` | `mcp_provider:delete` | Delete provider |

---

## MCP Tools

**Prefix:** `/mcp-tools`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/mcp-tools` | `mcp_tool:read` | List MCP tools |
| GET | `/mcp-tools/available` | `mcp_tool:read` | List available tools with categories |
| GET | `/mcp-tools/categories` | `mcp_tool:read` | List tool categories |
| GET | `/mcp-tools/categories/{category}` | `mcp_tool:read` | Get tools by category |
| GET | `/mcp-tools/{tool_id}` | `mcp_tool:read` | Get tool by ID |
| GET | `/mcp-tools/provider/{provider_id}` | `mcp_tool:read` | List tools by provider |
| POST | `/mcp-tools/sync` | `mcp_tool:sync` | Sync all tools from all providers |
| POST | `/mcp-tools/provider/{provider_id}/sync` | `mcp_tool:sync` | Sync tools from specific provider |
| DELETE | `/mcp-tools/{tool_id}` | `mcp_tool:sync` | Delete tool |

---

## Proxy

**Prefix:** `/api/proxy`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/proxy/mcp/tools` | user auth | List MCP tools from a server URL |
| GET | `/api/proxy/ollama/models` | user auth | List Ollama models |
| GET | `/api/proxy/rag/collections` | user auth | Proxy to RAG collections |
| GET | `/api/proxy/mcp/tools-builtin` | user auth | List tools from built-in tools-service |
| POST | `/api/proxy/mcp/execute` | user auth | Execute MCP tool |

---

## Web Search

**Prefix:** `/api/admin/web-search`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/admin/web-search/search-providers` | user auth | List search providers |
| GET | `/api/admin/web-search/content-providers` | user auth | List content providers |
| POST | `/api/admin/web-search/content-providers/test` | user auth | Test content provider |
| POST | `/api/admin/web-search/content-providers/crawl` | user auth | Crawl a URL |
| POST | `/api/admin/web-search/content-providers/reset-default` | user auth | Reset default content provider |
| POST | `/api/admin/web-search/content-providers/{id}/activate` | user auth | Activate content provider |
| POST | `/api/admin/web-search/content-providers/{id}/deactivate` | user auth | Deactivate content provider |

---

## Files

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/chat/file/{file_id}` | user auth | Serve file bytes (XLSX as CSV). In-memory cache, falls back to MinIO. |
| GET | `/api/chat/file/{file_id}/text` | user auth | Extract plain text from document (docx, pdf, pptx) |

---

## User / Projects

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/user/files/recent` | `project:read` | Get recent files |
| GET | `/api/llm/persona/{persona_id}/providers` | `provider:read` | Get persona LLM providers |
| GET | `/api/llm/provider` | `provider:read` | Get LLM provider config |
| GET | `/api/admin/llm/built-in/options` | `provider:read` | Get built-in LLM options |
| POST | `/api/admin/llm/test/default` | `provider:read` | Test default LLM |
| GET | `/api/user/projects` | `project:read` | Get user projects with chat sessions |
| POST | `/api/user/projects/create` | `project:create` | Create project |
| POST | `/api/user/projects/file/upload` | `project:update` | Upload files (multipart) |
| GET | `/api/user/projects/files/{project_id}` | `project:read` | Get project files |
| POST | `/api/user/projects/{project_id}/files/{file_id}` | `project:update` | Link file to project |
| DELETE | `/api/user/projects/{project_id}/files/{file_id}` | `project:update` | Unlink file from project |
| GET | `/api/user/projects/file/{file_id}` | `project:read` | Get user file |
| DELETE | `/api/user/projects/file/{file_id}` | `project:delete` | Delete file |
| POST | `/api/user/projects/file/statuses` | `project:read` | Get file statuses |
| GET | `/api/user/projects/{project_id}` | `project:read` | Get project with sessions |
| PATCH | `/api/user/projects/{project_id}` | `project:update` | Rename project |
| DELETE | `/api/user/projects/{project_id}` | `project:delete` | Delete project |
| GET | `/api/user/projects/{project_id}/details` | `project:read` | Get project details (files, personas) |
| GET | `/api/user/projects/{project_id}/instructions` | `project:read` | Get project instructions |
| POST | `/api/user/projects/{project_id}/instructions` | `project:update` | Upsert project instructions |
| GET | `/api/user/projects/{project_id}/token-count` | `project:read` | Get token count |
| POST | `/api/user/projects/{project_id}/move_chat_session` | `project:update` | Move session to project |
| POST | `/api/user/projects/remove_chat_session` | `project:update` | Remove session from project |

---

## Session context helpers

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/user/projects/session/{session_id}/token-count` | `chat:read` | Get session token count |
| GET | `/api/user/projects/session/{session_id}/files` | `chat:read` | Get session files |

---

## Admin LLM

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/admin/llm/provider` | `provider:read` | Get admin LLM provider config |
| POST | `/api/admin/llm/test` | `provider:read` | Test LLM |
| POST | `/api/admin/llm/default` | `provider:update` | Set default LLM |
| GET | `/api/admin/llm/ollama/available-models` | `provider:read` | List available Ollama models |
| PUT | `/api/admin/llm/provider` | `provider:update` | Save LLM provider |
| POST | `/api/admin/llm/provider` | `provider:create` | Create LLM provider |
| GET | `/llm/persona/{persona_id}/providers` | `provider:read` | Get persona providers |

---

## Permission reference

| Permission | Used by |
|---|---|
| `agent:assign` | Agent Groups |
| `agent:create`, `agent:delete`, `agent:list`, `agent:read`, `agent:update` | Agent Definitions |
| `agent:feedback` | Agents feedback |
| `agent:invoke`, `agent:stream` | Agents invoke/stream |
| `assistant:create`, `assistant:delete`, `assistant:read`, `assistant:search`, `assistant:update` | Assistants |
| `chat:delete`, `chat:read`, `chat:send` | Chat |
| `datasource:create`, `datasource:delete`, `datasource:sync`, `datasource:update` | Datasources |
| `mcp_provider:create`, `mcp_provider:delete`, `mcp_provider:read`, `mcp_provider:sync`, `mcp_provider:update` | MCP Providers |
| `mcp_tool:read`, `mcp_tool:sync` | MCP Tools |
| `persona:create`, `persona:delete`, `persona:read`, `persona:update` | Personas |
| `project:create`, `project:delete`, `project:read`, `project:update` | User/Projects |
| `provider:create`, `provider:delete`, `provider:read`, `provider:update` | Providers |
| `run:cancel`, `run:create`, `run:read` | Runs |
| `schedule:create`, `schedule:delete`, `schedule:update` | Sync Schedules |
| `thread:create`, `thread:delete`, `thread:read`, `thread:search`, `thread:update` | Threads |
