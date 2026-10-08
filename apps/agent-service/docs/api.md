# Agent Service API

**Service:** AI agent orchestration built on LangGraph, FastAPI, and Streamlit.
**Base URL:** `http://apisix:8000/agent-service` (via Apisix gateway) or `http://agent-service:8080` (direct)
**Canonical API prefix:** `/api/v1`
**Auth:** JWT Bearer token (except `/api/v1/health`). Internal calls use `X-Internal-Service-Token`.

This is the human-maintained endpoint contract for agent-service. Generated
OpenAPI output lives in `openapi.json` and is for schema-level checks, client
generation, and Swagger-style inspection.

Permissions are checked per-endpoint via `require_permission("<entity>:<action>")`.
Compatibility aliases are not supported: each handler exposes exactly one
canonical path, asserted by `tests/api/test_route_uniqueness.py`. New
integrations must use the canonical `/api/v1` paths documented here.

---

## Agent resource access

The agent catalog, detail, assignment options, connector resolution, and chat
execution use the same saved-persona access policy. Private agents require an
`execute`-capable direct or organization resource grant from user-service.
Resource IDs are saved numeric persona IDs serialized as strings. User-service
resolves either the local user UUID or the authenticated Keycloak subject.

Owners, public agents, built-in agents, and global administrators retain access.
The authoritative user-service permission response identifies global admins
with `is_admin` or the `*` permission. The `persona:update` action alone does not bypass resource
access. Legacy agent groups no longer authorize these surfaces. Permission
lookup failures grant no additional access.

Chat checks access before provider setup or thread changes. Numeric string IDs
are normalized, and active dynamic definition UUIDs resolve to their linked saved
persona before authorization. Generic agent invoke and stream endpoints check
the same linked-persona policy before loading configuration or streaming. Missing, unlinked, and unauthorized selections
return 404 without starting a stream.

## Agent connector bindings

You can assign multiple saved connector instances to a configurable MCP agent
alongside its ordinary tools. Configure credentials through the existing
connector form; the agent editor does not ask for credentials again.

Persona create, update, and read payloads include `connector_bindings`:

```json
{
  "base_agent": "configurable-mcp-agent",
  "mcp_tools": ["calculator"],
  "connector_bindings": [
    {
      "datasource_id": "e22ef0bf-3c16-4591-a254-7c48cb16fc55",
      "operations": ["list_resources", "read"]
    }
  ]
}
```

Each binding references an existing datasource UUID and at least one supported
operation. You can assign up to 32 distinct instances. Assignment requires
`datasource:read`; unsupported or deleted sources are rejected. Sending an empty
list removes connector assignments without removing ordinary tools. Omitting
the field on a legacy PATCH preserves existing bindings. Other base agents
cannot receive connector assignments.

`GET /api/v1/datasources/tool-options` lists configured instances with `id`,
`name`, `connector_type`, `operations`, and `unavailable_reason`. It does not
return credentials or the catalog of connectors available for installation.
An available adapter can still reject unsupported authentication or configuration
variants at execution time. See the
[tools-service connector contract](../../tools-service/docs/api.md).

Chat derives connector assignments from the saved persona and passes its ID
through trusted transport context. `POST
/api/v1/internal/connector-tools/resolve` requires the internal service token
and forwarded user identity. It checks current agent access, the saved operation
assignment, and the saved source before returning configuration to tools-service.
This endpoint is excluded from idempotency replay storage and responds with
`Cache-Control: no-store`.

The resolver reads the datasource's configuration from user-service, where it is
stored encrypted for the owning user, and translates it into the shape the
tools-service adapter reads. A connector or configuration variant the adapter
cannot handle is reported as unavailable instead of being resolved. No
credentials are stored in agent-service, agent bindings, chat messages, or
model-visible tool arguments.

## Idempotency

Mutating agent-service endpoints participate in the shared idempotency model.
Clients must send `Idempotency-Key` for `domain_required` routes. Reusing a key
with a different request fingerprint or principal returns
`409 idempotency_key_reused`.

`domain_required` routes include chat message send, run and agent streaming,
agent invoke routes, MCP tool execution proxy, datasource sync, ingest batch,
project file upload, mail test/send, provider model sync, Ollama pull/delete,
web crawl, and persona image upload. These routes reject missing keys with
`400 idempotency_key_required`.

`required_replay` routes include deterministic create operations for chat
sessions, threads, assistants, personas, agent definitions, agent groups,
datasources, MCP providers, provider configs, and user projects. They require
keys by default (`IDEMPOTENCY_ENFORCE_REQUIRED_KEYS=true`).

`optional_replay` applies to lower-risk mutations such as chat session rename.
Supplying a key enables replay and conflict detection.

---

## Health

| Method | Path             | Auth   | Description                             |
| ------ | ---------------- | ------ | --------------------------------------- |
| GET    | `/api/v1/health` | Public | Health check (includes Langfuse status) |

---

## Auth

Agent-service serves no `/api/v1/auth/*` endpoints. The web app reads the
current user from user-service (`/user-service/api/v1/auth/me`), and Gateway owns
login, token refresh, and logout.

_(The `GET /api/v1/admin/mcp/servers` stub was replaced by the MCP Server Admin API below.)_

---

## Agents

**Prefix:** `/api/v1/agents`

### Standard JSON responses

All 196 application JSON endpoints return the service-local
`core.http.response_models.ResponseModel[T]`. The original response DTO remains
nested under data. A successful response contains:

```json
{"statusCode": 200, "message": null, "data": [], "error": null}
```

`data` contains the endpoint's original payload. When a service raises a shared
application exception, the service propagates it to the route. The route sets
the HTTP status and returns the same model. For example, a missing agent returns
HTTP 404 and, for `X-Language: tr`:

```json
{"statusCode": 404, "message": "Ajan bulunamadı.", "data": null, "error": {"code": "agent.not_found", "message": "Ajan bulunamadı."}}
```

The exception stores a locale key (`errors.agent.not_found`); the route renders
the message for the request language. Frontend domain API functions check
`statusCode` and return `data` to their consumers. Authentication and validation
failures raised before the route body return the same ResponseModel fields.
Global framework errors preserve their existing safe public messages and codes;
idempotency errors also use this contract. Health/readiness/metrics keep their
native operational payloads, including top-level readiness diagnostics. Built-in Ollama missing-model deletion returns localized
404. Frontend domain consumers migrate with each endpoint group.

All 196 application JSON endpoints are migrated; follow the
[shared checklist](../../../docs/response-model-migration.md) for the inventory.
Creation retains HTTP 201 where declared; discard-draft acknowledgement returns
HTTP 200 with data null. Runtime serialization and consumer checks remain pending.

### Standard SSE events

`StreamEventModel[T]` lives beside ResponseModel. Producers serialize through
`to_sse()`, retaining existing data-only frames and event payload fields. Error
frames add `error: {code, message}` from error_contract locale keys, alongside
the existing type/content/error_code fields. The frontend prefers error.message.
The six SSE endpoints retain heartbeat comments and [DONE] sentinels. Failures
before streaming starts use the JSON HTTP error response; after it starts, a
localized event carries the failure without changing the already-sent status.
Raw file responses, health, readiness, and metrics retain their protocols.

| Method | Path                               | Permission       | Description                                           |
| ------ | ---------------------------------- | ---------------- | ----------------------------------------------------- |
| GET    | `/api/v1/agents/info`              | `agent:list`     | List all agents, models, default agent, default model |
| GET    | `/api/v1/agents/catalog`           | `persona:read`   | List lightweight product agent summaries              |
| GET    | `/api/v1/agents/{agent_id}`        | `persona:read`   | Get full product agent detail                         |
| POST   | `/api/v1/agents/{agent_id}/invoke` | `agent:invoke`   | Invoke agent — non-streaming response                 |
| POST   | `/api/v1/agents/{agent_id}/stream` | `agent:stream`   | Stream agent response (SSE events)                    |
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
| GET         | `/api/v1/chat/sessions`                              | `chat:read`   | List user's chat sessions             |
| POST        | `/api/v1/chat/sessions`                              | `chat:send`   | Create chat session                   |
| GET         | `/api/v1/chat/sessions/{session_id}`                 | `chat:read`   | Get session with messages             |
| DELETE      | `/api/v1/chat/sessions/{session_id}`                 | `chat:delete` | Delete chat session                   |
| DELETE      | `/api/v1/chat/delete-all-chat-sessions`              | `chat:delete` | Delete all user sessions              |
| PUT         | `/api/v1/chat/rename-chat-session`                   | `chat:send`   | Rename session                        |
| PUT         | `/api/v1/chat/update-chat-session-model`             | `chat:send`   | Update model override                 |
| PUT         | `/api/v1/chat/update-chat-session-temperature`       | `chat:send`   | Update temperature override           |
| POST        | `/api/v1/chat/stop-chat-session/{session_id}`        | `chat:send`   | Stop running session                  |
| POST        | `/api/v1/chat/messages`                              | `chat:send`   | Send message (streaming SSE response) |
| GET         | `/api/v1/chat/sessions/{session_id}/active-run`      | `chat:read`   | Get the session's in-flight run, if any |
| POST        | `/api/v1/chat/sessions/{session_id}/seen`            | `chat:read`   | Advance the session's read watermark (`last_accessed_at`) |
| GET         | `/api/v1/chat/runs/{run_id}/events`                  | `chat:read`   | Replay or follow a run's event stream (SSE) |
| POST        | `/api/v1/chat/create-chat-message-feedback`          | `chat:send`   | Create message feedback               |
| DELETE      | `/api/v1/chat/remove-chat-message-feedback`          | `chat:delete` | Remove message feedback               |
| GET         | `/api/v1/chat/available-context-tokens/{session_id}` | `chat:read`   | Get context tokens for session        |

One handler serves exactly one path: the `/api/v1/chat/sessions*` and
`/api/v1/chat/messages` routes are the canonical contract, and the earlier
verb-style aliases (`get-user-chat-sessions`, `create-chat-session`,
`get-chat-session`, `delete-chat-session`, `send-chat-message`) no longer exist.

The `chat/messages` endpoint handles: base64 file descriptors, LLM provider resolution (fetches provider API keys, base URLs), MinIO persistence, thread ownership checks.

### Resumable chat runs

`POST /api/v1/chat/messages` does not execute the agent in the response body.
The service registers a chat run and executes it in a supervisor-owned task, so
the response is only a subscriber: a client disconnect or reload ends the
subscription, never the run. The response carries the `X-Chat-Run-Id` header.
The SSE wire contract is unchanged except for additions:

- Every sequenced frame starts with `id: <seq>` (an integer, starting at 1).
  Clients resume by sending the last received `seq` back.
- A `run_started` meta packet (frame 1) opens the stream and a `run_end` meta
  packet carries the terminal status (`completed`, `failed`, `cancelled`, or
  `interrupted`). `data: [DONE]` is always the last frame, exactly once.
- A `caught_up` meta packet (no `id:`, never stored in the event log) marks
  the end of replay: the reader sends it once, the first time the log has
  nothing after the last delivered event. Everything before it was history;
  everything after it is the live tail. A stream that ends while still
  replaying (a finished run, a `resync`, an expired run) sends none, so
  clients treat the end of the stream as caught up too.

While a run is active for a thread, a second send is rejected before any
side effect with `409` and the error code `chat_run.active`; the holder's
`run_id` is in `error.details.run_id`. If the run registry or event log is
unreachable, sends answer `503` with `chat_run.unavailable` and never leave a
dangling lock. Both use the standard `ResponseModel` error envelope with a
localized `error.message`.

`GET /api/v1/chat/sessions/{session_id}/active-run` reports the session's
in-flight run (`{"active_run": null}` when idle). `GET
/api/v1/chat/runs/{run_id}/events` replays the run's full event stream from the
beginning or from `Last-Event-ID` (which wins over `?after=`); a malformed
resume id answers `422`, an unknown or foreign run answers `404`. Both endpoints
enforce session and run ownership. Stop is owner-checked: only the session's
owner can stop it, and a Stop issued from any instance reaches the run's owner
through a Redis cancel flag within the heartbeat interval. A run on the
instance that receives the Stop is stopped even if the Redis registry is down;
only a Stop that cannot be recorded and has no local run answers `503`
(`chat_run.unavailable`).

Stop accepts an optional `?client_request_id=` (the send's `Idempotency-Key`).
It reaches a send whose run isn't registered yet: the service records a
short-lived mark for that request before it looks up the active run, and the
supervisor checks the mark after acquiring the thread, so the agent never
starts. Once a Stop is recorded, the run's cooperative cancel event is set
(also for a generator that registers it later) and no further `token`,
`reasoning_delta`, or `flow_stage_output_delta` frame is written to the event
log.

`GET /api/v1/chat/sessions` marks each session with `has_active_run` (a run is
still generating its answer). `POST /api/v1/chat/sessions/{session_id}/seen`
moves `last_accessed_at` to now once a client has shown a finished answer, so
the sidebar's unread dot clears; it answers `404` for a session the caller does
not own. A finished answer is stamped into `last_message_at` with the instant
its run finished (never moved backward), so a later `seen` is always newer than
the answer whichever of the two requests reaches the database first.

Chat session list and detail responses include `time_created`, `time_updated`,
`last_message_at`, and `last_accessed_at`. Use `last_message_at` for
conversation activity ordering. If the field is present and `null`, the session
has no accepted user-message activity and orders by `time_created`. Use
`last_accessed_at` only for read telemetry; opening a chat must not move it in
Recents or project chat lists. The list endpoints accept `page_size`,
`before_activity`, and `before_id` for activity-keyset pagination and return
`next_cursor` with the same cursor field names when another page is available.

`GET /api/v1/chat/sessions` also accepts `q` (at most 200 characters), a
case-insensitive match on the stored session name, and `agents_only=true`, which
drops plain-model chats (no `persona_id`, or `0`) and keeps agent and flow
sessions. Both filters apply before pagination, so the cursor pages through the
filtered set. Unnamed sessions (no stored name, or the default placeholder name) are not
matched by `q`.

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
| GET    | `/api/v1/datasources/connectors`                 | `datasource:read`   | List source connectors (filter: `category`, `search`)         |
| GET    | `/api/v1/datasources/connectors/{name}/spec`     | `datasource:read`   | Get connector JSON Schema config spec                         |
| POST   | `/api/v1/datasources/connectors/{name}/validate` | `datasource:create` | Validate connector config                                     |
| POST   | `/api/v1/datasources/connectors/{name}/streams`  | `datasource:create` | Get available streams for connector                           |
| GET    | `/api/v1/datasources`                            | `datasource:read`   | List configured datasources                                   |
| POST   | `/api/v1/datasources`                            | `datasource:create` | Create datasource (stores its config for the caller)          |
| GET    | `/api/v1/datasources/{id}/details`               | `datasource:read`   | Get datasource details with paginated chunks                  |
| PUT    | `/api/v1/datasources/{id}`                       | `datasource:update` | Update datasource; a changed `connector_config` forgets the saved incremental checkpoints |
| POST   | `/api/v1/datasources/{id}/sync`                  | `datasource:sync`   | Trigger sync                                                  |
| GET    | `/api/v1/datasources/{id}/status`                | `datasource:read`   | Get sync status                                               |
| GET    | `/api/v1/datasources/{id}/sync-history`          | `datasource:read`   | Get sync job history                                          |
| DELETE | `/api/v1/datasources/{id}`                       | `datasource:delete` | Delete datasource and the chunks rag-service holds for it     |

Connectors are the in-process sources of `packages/connector-py`; `connector_type`
is the connector's name (`postgres`, `s3`, `confluence`, ...). Catalog entries
carry `name`, `display_name`, `category`, `icon_url` (an inline SVG data URI),
`documentation_url`, and `is_available`.

`GET .../connectors/{name}/spec` returns the schema the configuration form is
rendered from: a flat JSON Schema (no `$ref`), optional fields without a `null`
variant, secrets flagged `x-secret` / `writeOnly`, and fields that have no form
widget (mappings, lists of objects) as JSON text areas flagged `x-json`. A
mapping that may hold credentials next to ordinary values (`headers`, `params`,
driver options) is also flagged `x-sensitive-keys`.
`validate`, `streams`, create, and update accept the form's values, including
JSON text for those fields.

The configuration is stored encrypted in user-service for the calling user;
agent-service keeps a reference only. `GET .../{id}/details` returns it in
`config`, secrets replaced by `********`, only to callers who also hold
`datasource:update`. For every other caller `config` is `{}` and the stored
configuration is not read; the rest of the response is the same. Inside an
`x-sensitive-keys` mapping the keys are shown and the mask replaces what a key
named like a credential holds (`Authorization`, `X-Api-Key`, `client_secret`,
`token`, `password`, ...), at any depth; a credential under a name that does
not say so is returned as it is. Sending the mask back on `PUT` keeps the
stored secret, entry by entry inside such a mapping; a mask for a secret that
is not stored in that place is answered 400. A datasource created before the
in-process connectors has no stored configuration: `PUT` with
`connector_config` attaches one, and until then sync answers 400. The same
`PUT` stores the configuration anew when the stored one has gone missing.

`POST .../{id}/sync` starts a background job and returns at once with
`"status": "Sync started"`. A datasource has at most one pending or running
job: while one exists the call starts nothing, changes nothing and answers
`"status": "Already syncing or queued"`. It answers 400 when the datasource has
no connection or its stored configuration is missing. At most
`CONNECTOR_MAX_CONCURRENT_SYNCS` jobs run at a time; `GET .../{id}/status`
reports `queue_position` for a waiting job. `?full_refresh=true` starts the
job with every stream read from the start: the saved incremental checkpoints
are forgotten before the first record is read, also when that job fails, so
the following run starts over as well. A `PUT` whose `connector_config`
differs from the stored one forgets them too: a connection pointed at another
server or database must not skip rows. The destination modes are unchanged:
`overwrite` streams retire the previous run's chunks when the job finishes,
`append` streams replace records by key. `sync-history` rows are this
service's own jobs (`created_at`/`updated_at` in epoch seconds, `bytes_synced`
always 0). `last_error` (details, status, and the `PUT` answer) and
`error_message` (sync history) carry the reason of a failed sync only for
callers who also hold `datasource:sync`; every other caller reads "The sync
did not complete. The reason is shown to users who can run syncs." in its
place. The reason has its credentials removed: URL query strings, URL
passwords, the values of the connector's secret fields and what the credential
keys of its `x-sensitive-keys` mappings hold appear as `***`.

---

## Sync Schedules

**Prefix:** `/api/v1/datasources`

| Method | Path                                       | Permission        | Description                                       |
| ------ | ------------------------------------------ | ----------------- | ------------------------------------------------- |
| GET    | `/api/v1/datasources/schedules`            | `schedule:read`   | List all sync schedules                           |
| POST   | `/api/v1/datasources/{id}/schedule`        | `schedule:create` | Create sync schedule (cron, run by the scheduler) |
| GET    | `/api/v1/datasources/{id}/schedule`        | `schedule:read`   | Get schedule for datasource                       |
| PUT    | `/api/v1/datasources/{id}/schedule`        | `schedule:update` | Update schedule                                   |
| DELETE | `/api/v1/datasources/{id}/schedule`        | `schedule:delete` | Delete schedule (set to manual)                   |
| GET    | `/api/v1/datasources/{id}/schedule/status` | `schedule:read`   | Get combined sync + schedule status               |

`PUT` takes a partial body: a field left out keeps its value. In particular a
body without `enabled` leaves the switch as it is, so changing the cron or
`update_graph_rag` of a disabled schedule does not arm it; the definition is
still validated and is what `enabled: true` arms later.

---

## Ingestion

| Method | Path                     | Auth            | Description                                                                      |
| ------ | ------------------------ | --------------- | -------------------------------------------------------------------------------- |
| POST   | `/api/v1/ingest/source-preview` | `datasource:update` | Live stream schemas of a datasource's connector |

Each stream carries `name`, `key_properties`, `schema` and `field_count`.
`field_count` is the number of fields the connector declares for the stream, or
`null` when it declares none: most API connectors publish no schema, which
means "unknown", not "no fields".

---

## MCP Server Admin (frontend-facing)

Atlas-shaped surface backing `apps/web` → `mcpService.ts`. Server ids are the
`int_id` surrogate; the built-in tools server is always returned as `id: 1`.
External MCP server tools load into agent runs with the acting user's stored
credentials (`MCP_EXTERNAL_ENABLED`).

MCP administration preserves typed authentication, URL validation, and dependency
failures through the standard response envelope. Public `error.message` values
use the requested language. A missing tool returns 404, rejected server URLs
return 422, and dependency timeouts return 504. Circuit-breaker failures retain
503 and retry metadata while using a localized message. Unknown external tool
execution failures retain the existing localized `data.error` result contract.

| Method | Path                                                   | Permission            | Description                                                       |
| ------ | ----------------------------------------------------- | --------------------- | --------------------------------------------------------------- |
| GET    | `/api/v1/admin/mcp/servers`                            | `mcp_provider:read`   | List servers as `MCPServer` DTOs (built-in + external)          |
| GET    | `/api/v1/admin/mcp/servers/{int_id}`                   | `mcp_provider:read`   | Single server incl. masked credentials                          |
| POST   | `/api/v1/admin/mcp/server/validate`                    | `mcp_provider:create` | Probe `{server_url}` as MCP without persisting → `{valid, auth_required, tool_count}` |
| POST   | `/api/v1/admin/mcp/server`                             | `mcp_provider:create` | Create external server `{name, description?, server_url}`; rejects a URL that does not answer an MCP handshake with `422` |
| PATCH  | `/api/v1/admin/mcp/server/{int_id}`                    | `mcp_provider:update` | Update `{name?, description?, server_url?}`                     |
| DELETE | `/api/v1/admin/mcp/server/{int_id}`                    | `mcp_provider:delete` | Delete server + its tools + credentials                         |
| PATCH  | `/api/v1/admin/mcp/server/{int_id}/status?status=`     | `mcp_provider:update` | Set status enum                                                 |
| GET    | `/api/v1/admin/mcp/server/{int_id}/tools/snapshots`    | `mcp_provider:sync`   | Discover tools (with auth), return `ToolSnapshot[]`             |
| GET    | `/api/v1/admin/mcp/servers/{int_id}/tools`             | `mcp_tool:read`       | Tools last synced from the server (`ToolSnapshot[]`); database read only, never contacts the server or changes its status |
| POST   | `/api/v1/admin/mcp/servers/create`                     | `mcp_provider:update` | Upsert auth config (API token / OAuth client / template)       |
| POST   | `/api/v1/admin/mcp/servers/{int_id}/connect`           | `mcp_provider:connect`| Bind credentials to a registered provider (`{transport?, auth_type, auth_performer?, api_token?, auth_template?, admin_credentials?, oauth_client_id?, oauth_client_secret?}`; no url) and sync its tools |
| DELETE | `/api/v1/admin/mcp/servers/{int_id}/connect`           | `mcp_provider:connect`| Disconnect: drop the shared and per-user credentials and cached tools and return the provider to `CREATED` (the registration is kept) |
| POST   | `/api/v1/admin/mcp/oauth/connect`                      | `mcp_provider:update` | Begin OAuth (discovery + DCR + PKCE) → `{oauth_url}`           |
| POST   | `/api/v1/mcp/oauth/callback?code=&state=`              | user auth             | Complete OAuth code exchange → `{redirect_url, server_name}`    |
| PATCH  | `/api/v1/admin/tool/status`                            | `mcp_provider:update` | Toggle tools `{tool_ids: int[], enabled}`                       |

`mcp_provider:configure` has no endpoint: it gates the web MCP Configuration page (system admin registers providers there, using `create`/`update`/`delete`). Enterprise admins hold `mcp_provider:connect` only: they pick a registered provider, bind credentials (`POST …/connect`) and unbind them (`DELETE …/connect`), but never enter a url.

---

## MCP Providers

**Prefix:** `/api/v1/mcp-providers` — internal/programmatic; shares `MCPProviderService` with the admin surface above.

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

Mail configs are system-wide SMTP server settings managed through admin-only
permission checks. The creator ID remains available for audit purposes but
doesn't restrict which configs another authorized administrator can list or
manage. Responses never include SMTP passwords. The service stores encrypted
secrets and only resolves them at runtime when an agent calls `send_email`.

| Method | Path                                    | Auth      | Description                                                           |
| ------ | --------------------------------------- | --------- | --------------------------------------------------------------------- |
| GET    | `/api/v1/mail-configs`                  | `mail_config:read`   | List all active system SMTP mail configs                              |
| POST   | `/api/v1/mail-configs`                  | `mail_config:create` | Create an SMTP mail config with encrypted password storage            |
| GET    | `/api/v1/mail-configs/{config_id}`      | `mail_config:read`   | Get a masked mail config by ID                                        |
| PATCH  | `/api/v1/mail-configs/{config_id}`      | `mail_config:update` | Update an SMTP mail config; omit `password` to keep the stored secret |
| DELETE | `/api/v1/mail-configs/{config_id}`      | `mail_config:delete` | Deactivate a mail config                                              |
| POST   | `/api/v1/mail-configs/{config_id}/test` | `mail_config:test`   | Send a test email through the selected SMTP config                    |
| POST   | `/api/v1/mail-configs/{config_id}/send` | `mail_config:send`   | Send an email through the selected SMTP config                        |
| GET    | `/api/v1/mail-configs/user-credentials` | Authenticated user | Get masked personal SMTP credentials |
| PUT    | `/api/v1/mail-configs/user-credentials` | Authenticated user | Save personal SMTP credentials |
| DELETE | `/api/v1/mail-configs/user-credentials` | Authenticated user | Deactivate personal SMTP credentials |
| POST   | `/api/v1/mail-configs/user-credentials/test` | Authenticated user | Test saved personal SMTP credentials |

Personal credential saves with invalid settings and tests without saved
credentials return `400` with the `request.invalid` error code.

`POST /api/v1/mail-configs/{config_id}/send` accepts the same safe email
payload used by the playground: `to`, `subject`, `body`, optional `cc`, `bcc`,
`is_html`, `reply_to`, and optional `attachments`. Each attachment object must
include `filename`, `mime_type`, and `content_base64`.

Mail failures use the standard response envelope with a localized `error.message`
and a stable `error.code`. Invalid payloads and refused recipients return 400;
SMTP authentication and message rejection return 502; connection failures return
503; timeouts return 504; missing server configuration returns 500. Oversized
attachments retain 413. SMTP diagnostic text is not returned as a user message.

---

## Proxy

**Prefix:** `/api/v1/proxy`

| Method | Path                              | Auth      | Description                            |
| ------ | --------------------------------- | --------- | -------------------------------------- |
| GET    | `/api/v1/proxy/mcp/tools`         | `mcp_tool:read`   | List MCP tools from a server URL       |
| GET    | `/api/v1/proxy/ollama/models`     | `provider:read`   | List Ollama models                     |
| GET    | `/api/v1/proxy/rag/collections`   | `collection:list` | Proxy to RAG collections               |
| GET    | `/api/v1/proxy/mcp/tools-builtin` | `mcp_tool:read`   | List tools from built-in tools-service |
| POST   | `/api/v1/proxy/mcp/execute`       | `tool:execute`    | Execute MCP tool                       |

---

## Web Search

**Prefix:** `/api/v1/admin/web-search`

| Method | Path                                                         | Auth      | Description                    |
| ------ | ------------------------------------------------------------ | --------- | ------------------------------ |
| GET    | `/api/v1/admin/web-search/search-providers`                  | `web_search:manage` | List search providers          |
| GET    | `/api/v1/admin/web-search/content-providers`                 | `web_search:manage` | List content providers         |
| POST   | `/api/v1/admin/web-search/content-providers/test`            | `web_search:test` | Test content provider          |
| POST   | `/api/v1/admin/web-search/content-providers/crawl`           | `web_search:manage` | Crawl a URL                    |
| POST   | `/api/v1/admin/web-search/content-providers/reset-default`   | `web_search:manage` | Reset default content provider |
| POST   | `/api/v1/admin/web-search/content-providers/{id}/activate`   | `web_search:manage` | Activate content provider      |
| POST   | `/api/v1/admin/web-search/content-providers/{id}/deactivate` | `web_search:manage` | Deactivate content provider    |

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

- Rendering: `service/DocumentGenerationService.py` is a thin façade —
  `from service import DocumentGenerationService as docgen` still works
  unchanged, but the implementation lives in the `service/documents/` package,
  split by concern: `blocks.py`/`markdown_parser.py` (the Markdown → block
  tree, including inline bold/italic/code/link spans), `options.py` (the
  `DocumentOptions`/`SpreadsheetOptions` schema), `themes.py` (named
  theme→font/color resolution), `numbering.py` (heading and table/figure
  caption numbering, shared by both renderers so DOCX and PDF stay
  consistent), `docx_renderer.py`/`pdf_renderer.py`/`xlsx_renderer.py`/`text_renderer.py`
  (one renderer per output format), plus `ooxml.py`, `pdf_fonts.py`,
  `pdf_canvas.py`, `header_footer.py`/`pdf_header_footer.py`, and
  `image_loading.py` for the low-level pieces each renderer needs. PDF
  Unicode text (Turkish characters) requires the `DejaVuSans` family of TTF
  fonts, installed via `fonts-dejavu-core` in `docker/Dockerfile.service`;
  `pdf_fonts.py` maps a requested Word-style family name (`Calibri`,
  `Georgia`, `Consolas`, …) to the closest registered DejaVu bucket
  (sans/serif/mono), and falls back to the regular file when a bold/italic
  variant TTF is missing rather than to base-14 Helvetica — Helvetica can't
  render Turkish glyphs, so silently substituting it would defeat the reason
  DejaVu was registered in the first place.
- Styling: both tools accept an optional `options` argument (a dict, or a
  JSON string — either is accepted) that controls theme, fonts and colors,
  page size/orientation/margins, cover page, table of contents, heading
  numbering, header/footer (including `{page}`/`{pages}`/`{title}`/`{date}`/`{version}`
  placeholders), table styling, watermark, and PDF bookmarks/metadata for
  `create_document`; and theme, header row styling, freeze pane, autofilter,
  zebra striping, column widths/formats/alignments, and static conditional
  cell shading for `create_spreadsheet`. Five built-in themes ship in
  `themes.py`: `default`, `corporate_blue`, `minimal_gray`, `academic`, and
  `dark_accent`. Parsing in `options.py` is deliberately tolerant: an unknown
  key or an invalid value is logged and replaced with its default rather than
  rejecting the call — a long document is too expensive to make the user
  regenerate over one bad style field. `DOCUMENT_TOOLS_RICH_OPTIONS` (see
  `core/settings.py`) controls how much of this the model is told about: on
  (the default), the tool description carries the full `options` reference
  (~350 tokens); off, it gets a short description instead — `options` still
  works either way, the model just isn't walked through every field for
  token-sensitive or small local-model setups.
- Table of contents, by format: DOCX gets a real Word TOC field (`\o \h \z \u`)
  with a cached heading list — no page numbers, since those aren't known yet
  either — rendered in between, plus `updateFields` set in the document
  settings. The cache exists because
  `docx-preview` — what the web frontend uses to render the file inline —
  does not evaluate fields, so a bare field would show as empty until the
  file is opened in Word or LibreOffice; the cached list is what renders in
  the browser, and Word overwrites it with real page numbers on open. PDF has
  no such split-brain viewer problem, so its TOC is a genuine ReportLab
  `TableOfContents` flowable built through `document.multiBuild(...)`, giving
  real resolved page numbers directly in the generated file — see
  `pdf_renderer.py`. PDF header/footer `{pages}` (the *total* page count)
  has a similar timing problem of its own: ReportLab renders one page at a
  time and has no idea how many pages the finished document will have until
  the end, so that placeholder is resolved by `pdf_canvas.NumberedCanvas`,
  which defers drawing until the whole document has been laid out.
- DOCX header/footer left/center/right positioning uses a borderless
  3-column table (`header_footer.render` in `header_footer.py`), not `w:tabs`
  tab stops. Custom tab-stop positions are not reliably honored by every DOCX
  viewer — in particular `docx-preview` — so a center/right-aligned segment
  (typically the `{page} / {pages}` field) could render left-aligned near the
  margin instead of where it was positioned. Table columns render
  consistently across viewers.
- Each heading gets a Word bookmark (`ooxml.add_bookmark`), and each cached
  DOCX TOC entry is a real internal hyperlink to the matching bookmark
  (`ooxml.add_internal_hyperlink_run`), not just plain text. This makes TOC
  navigation work by construction rather than relying on Word regenerating
  hyperlinked entries when it recalculates the field — which also means
  clicking a TOC entry works in the cached preview shown by non-field-evaluating
  viewers, not only after Word updates the field.
- Known limitation, browser preview only: `docx-preview` has no real
  pagination engine — per its own documentation, it only inserts a page break
  at an explicit `<w:br w:type="page"/>`, a `pageBreakBefore` paragraph
  property, or a cached `w:lastRenderedPageBreak` marker that MS Word itself
  writes while laying out a document it has open. A document generated here
  and never opened in Word carries none of the latter, so any stretch of body
  content that doesn't cross one of our own explicit page breaks (from a
  `<!-- pagebreak -->` marker, or the ones automatically inserted after the
  cover page and TOC) renders in the browser as a single tall `min-height`
  block instead of Word's correctly paginated multi-page layout — visible as
  a page that looks too tall, fewer apparent pages than the downloaded file
  has, and a `{page}` field that only ever shows its cached fallback value
  since the browser only ever rendered one page-group. The downloaded file is
  unaffected — Word and LibreOffice paginate it correctly on open, because
  they compute real page breaks instead of relying on cached hints. Fixing
  the in-browser preview would mean either estimating page breaks
  server-side and inserting them explicitly, or round-tripping the file
  through a real layout engine (e.g. headless LibreOffice) before preview;
  neither has been done, so treat the browser preview's page count/height as
  approximate for freshly generated files.
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
  `recover_document_tool_args` repairs the shapes local models produce most
  often — the body under an alias key (`text`, `body`, `markdown`, …) or inlined
  as `<content>…</content>` inside an unrelated argument — because rejecting
  those costs the user a full regeneration of a long document. It only ever
  *adds* `content`; a description-shaped argument is never promoted to the body,
  so genuinely wrong calls still fail loudly. It also gathers style keys a
  model dropped at the top level instead of nesting them under `options` (for
  example `theme="corporate_blue"` alongside `filename`/`format`/`content`)
  into `options`, merging with — and yielding to — any `options` the model did
  provide explicitly. Two related guards:
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
  (`service/AgentStreamService.py`'s `message_generator`) and the chat-history rebuild path
  (`service/chat/chat_management_service.py`) recognize this via the shared
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

## Document drafts (versioned editing)

Every document/spreadsheet the tools above create is also a versioned draft:
each `create_document`/`create_spreadsheet`/`edit_document`/`rewrite_document`
call appends an immutable `Revision` to an `AuthoredDocument` aggregate
(`service/authored_documents/`, tables `authored_documents` /
`authored_document_revisions`, migration `0049_authored_documents`). The
`document` table stays the rendered-file store used by `file_route.py` — a
revision only points at its render through `rendered_file_id`, indexed so
`/by-file` can resolve a chat card back to its draft. Deleting a thread deletes
its drafts and revisions (`ON DELETE CASCADE`, migration 0050).

All routes below (`api/routes/authored_documents_route.py`) sit behind
`require_user` and are owner-scoped through `AuthoredDocumentService`; DTOs
are in `schemas/authored_documents.py`. Domain errors
(`core/exceptions/authored_documents.py`) subclass the shared
`error_contract` classes, so the app's global handler produces the HTTP
status/code/message/details envelope below without route-level translation.

| Method | Path                                                         | Description                                                                 |
| ------ | ------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| GET    | `/api/v1/documents?thread_id=`                                | List documents authored in one thread, most-recently-updated first.        |
| GET    | `/api/v1/documents/{document_id}`                              | Document metadata + every revision's summary (no content).                 |
| GET    | `/api/v1/documents/{document_id}/revisions/{revision_no}`      | One revision's full content, options, stats, `rendered_file_id`.            |
| GET    | `/api/v1/documents/by-file/{file_id}`                          | Resolve a rendered `file_id` (e.g. a chat card) back to `document_id` / `revision_no`. 404 (`details.file_id`) for a legacy (pre-draft) file. |
| POST   | `/api/v1/documents/{document_id}/revisions`                    | Save a user edit: `{base_revision_no, content, summary?}` → new revision (`operation=user_edit`). |
| POST   | `/api/v1/documents/{document_id}/revisions/{revision_no}/restore` | `{base_revision_no}` → new revision copying an older one's content (`operation=restore`). |
| GET    | `/api/v1/documents/{document_id}/revisions/{revision_no}/export?format=` | On-demand render of a revision to another format of the same kind (`pdf`/`docx`/`md`/`txt`/`json`/`xlsx`/`csv`), streamed; not saved as a new revision. |

- `POST /revisions` and `.../restore` both take `base_revision_no` for
  optimistic concurrency against `head_revision_no`: a stale base raises
  `RevisionConflictError` (409, `document.revision_conflict`, details carry
  `base_revision_no`/`head_revision_no`) so the caller can reload and retry.
  An edit whose content and metadata are unchanged from head raises
  `NoChangeError` (422, `document.no_change`); invalid Mermaid fences raise
  `DiagramValidationError` (422, `document.diagram_invalid`, details carry
  per-block `block_index`/`document_line`/`line`/`message`).
- A Markdown draft may embed an image the user attached to the chat as
  `![alt](attachment:<file_id>)`. Saving resolves every reference for the
  caller only; an unknown, foreign, non-image or over-5-MiB one raises
  `AttachmentReferenceError` (422, `document.attachment_invalid`, details carry
  `file_ids`) and nothing is saved. `pdf`/`docx` renders embed the image; an
  export whose attachment has since vanished leaves the image out; `md`/`txt`
  keep the reference text. The panel loads it from `GET /api/chat/file/{id}`.
- `export` accepts any `ExportFormat` value at the transport layer (FastAPI
  rejects an unknown one as a plain 422 before the route body runs), but a
  cross-kind conversion the service can't perform (e.g. rendering a
  spreadsheet revision as `pdf`) raises `UnsupportedFormatChangeError` (422,
  `document.format_change_unsupported`) — same envelope, service-level
  reason.
- Response shape for both mutating routes (`RevisionMutationResponse`):
  `{document: DocumentSummaryDTO, revision: RevisionSummaryDTO, file: RenderedFileRefDTO, diagram_check}`,
  where `diagram_check` is `passed` \| `skipped` \| `not_applicable` (`skipped`
  when the Mermaid renderer timed out or its process pool failed to start —
  see the diagram settings below; the diagram still exports as a labelled
  code block rather than blocking the save).
- Agent-side tools (`agents/tooling/document_*_tools.py`) operate on the same
  service and revisions: `list_documents`, `list_attachments` (the
  thread's attached images and their `attachment:` markdown), `read_document`
  (quiet, no timeline/progress packets), `edit_document` (content-anchored `old_str`/
  `new_str` edits, never line-anchored), `rewrite_document` (full
  replacement). The four writers share the `create_document`/`create_spreadsheet`
  wire format plus revision fields — see the stream contract in
  `docs/service-interactions.md`.

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
| `agent:create`, `agent:delete`, `agent:list`, `agent:read`, `agent:update`                                    | Agent Definitions    |
| `agent:feedback`                                                                                              | Agents feedback      |
| `agent:invoke`, `agent:stream`                                                                                | Agents invoke/stream |
| `assistant:create`, `assistant:delete`, `assistant:read`, `assistant:search`, `assistant:update`              | Assistants           |
| `chat:delete`, `chat:read`, `chat:send`                                                                       | Chat                 |
| `datasource:create`, `datasource:delete`, `datasource:read`, `datasource:sync`, `datasource:update`           | Datasources          |
| `mail_config:create`, `mail_config:delete`, `mail_config:read`, `mail_config:send`, `mail_config:test`, `mail_config:update` | Mail configs         |
| `mcp_provider:create`, `mcp_provider:delete`, `mcp_provider:read`, `mcp_provider:sync`, `mcp_provider:update` | MCP Providers        |
| `mcp_tool:read`, `mcp_tool:sync`                                                                              | MCP Tools            |
| `persona:create`, `persona:delete`, `persona:read`, `persona:update`                                          | Personas             |
| `project:create`, `project:delete`, `project:read`, `project:update`                                          | User/Projects        |
| `provider:create`, `provider:delete`, `provider:read`, `provider:update`                                      | Providers            |
| `run:cancel`, `run:create`, `run:read`                                                                        | Runs                 |
| `schedule:create`, `schedule:read`, `schedule:update`, `schedule:delete`                                       | Sync Schedules       |
| `thread:create`, `thread:delete`, `thread:read`, `thread:search`, `thread:update`                             | Threads              |
| `web_search:manage`, `web_search:test`                                                                          | Web Search Admin     |

---

## Flow Canvas & Versions

Spans two prefixes: `/api/v1/flow-components` (component catalog) and
`/api/v1/agent-definitions` (draft/version/playground endpoints, alongside
Agent Definitions above).

| Method | Path | Permission | Description |
| ------ | ---- | ---------- | ----------- |
| GET | `/api/v1/flow-components` | `flow:read` | List all registered component templates grouped by category |
| GET | `/api/v1/flow-components/{component_type}` | `flow:read` | Get detail for a single component template |
| GET | `/api/v1/flow-components/options/{source}` | `flow:read` | Dynamic options resolver for select inputs |
| POST | `/api/v1/agent-definitions/validate-flow` | `flow:read` | Validate a FlowSpec graph topology |
| GET | `/api/v1/agent-definitions/{definition_id}/flow/draft` | `flow:read` | Get draft FlowSpec for an agent definition |
| PUT | `/api/v1/agent-definitions/{definition_id}/flow/draft` | `flow:update` | Save draft FlowSpec |
| GET | `/api/v1/agent-definitions/{definition_id}/flow/versions` | `flow:read` | List published versions history |
| POST | `/api/v1/agent-definitions/{definition_id}/flow/publish` | `flow:publish` | Publish current draft as a new immutable version |
| POST | `/api/v1/agent-definitions/{definition_id}/flow/rollback` | `flow:publish` | Rollback draft to a previously published version |
| POST | `/api/v1/agent-definitions/{definition_id}/flow/playground/runs/stream` | `flow:execute` + `flow:update` | Stream execution of a draft flow in the playground (400 with `errors[]` — same shape as publish — when the draft fails structural validation, e.g. an entry→exit path that only runs through resource nodes) |
