# Tools Service (MCP Server) API

**Service:** MCP (Model Context Protocol) tool server — code execution, file operations, git, search, Docker, and more.
**Base URL:** `http://kong:8000/tools-service/mcp` (via Kong, JWT required) or `http://tools-service:8003/mcp` (direct)
**Auth:** 3-tier — JWT (Keycloak) > Internal Token > API Key. All tools require `tool:execute` scope.

This is the human-maintained MCP transport and tool contract for tools-service.
Prefer generated API artifacts only when you need schema-level detail.

---

## Transport

The service uses **FastMCP HTTP transport**. The MCP protocol endpoint is at `/mcp`.
Kong forwards `/tools-service/mcp` to that transport. Internal callers use
`/internal/tools-service/mcp`.

`GET /tools-service/health` is public through Kong and forwards to the
FastMCP custom `/health` route.

| Endpoint      | Method | Auth         | Description                                   |
| ------------- | ------ | ------------ | --------------------------------------------- |
| `GET /mcp`    | GET    | Bearer token | MCP discovery / SSE connection                |
| `POST /mcp`   | POST   | Bearer token | MCP JSON-RPC (list tools, execute tool, etc.) |
| `GET /health` | GET    | Public       | Health check `{"status": "ok"}`               |

---

## Idempotency

`POST /mcp` is `domain_required` because JSON-RPC tool execution can run shell,
file, Git, Docker, email, web, and other side-effecting tools. However, MCP
streamable-HTTP sessions issue many POSTs (`initialize`, `tools/list`,
`tools/call`) that all share the client's connection headers, so a static
`Idempotency-Key` cannot represent a single logical operation. The middleware
therefore does not require a key on `/mcp` (`enforce_missing_key=false`); when
a key is supplied it is still honored for replay and conflict detection.

The FastMCP HTTP app is wrapped with the shared idempotency middleware. Reusing
a key with a different request fingerprint or principal returns
`409 idempotency_key_reused`. Non-replayable tool execution marks the key as
completed without replay so a retry cannot execute the same tool call again.

---

## Tool categories

17 tool categories auto-discovered at startup via `ToolRegistry.discover_plugins()`.

### Calculator

| Tool        | Parameters        | Description                                                                                                                                              |
| ----------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `calculate` | `expression: str` | Safely evaluate math expressions. Supports: `abs, round, min, max, sum, pow, sqrt, sin, cos, tan, log, log10, exp, pi, e`. Rejects dangerous characters. |

### Code Execution

| Tool                 | Parameters                                                               | Description                                        |
| -------------------- | ------------------------------------------------------------------------ | -------------------------------------------------- |
| `run_python`         | `code: str`, `timeout?: int = 30`                                        | Run Python code, returns stdout+stderr             |
| `run_python_file`    | `file_path: str`, `args?: str`, `timeout?: int = 60`                     | Run existing Python file with CLI args             |
| `validate_python`    | `code: str`                                                              | Validate Python syntax via `ast.parse()`           |
| `run_node`           | `code: str`, `timeout?: int = 30`                                        | Run Node.js code                                   |
| `run_pytest`         | `test_path: str`, `args?: str`, `timeout?: int = 120`                    | Run pytest on file/directory                       |
| `run_npm_command`    | `project_dir: str`, `command: str`, `timeout?: int = 120`                | Run npm command in project                         |
| `validate_json_file` | `file_path: str`                                                         | Validate JSON file                                 |
| `run_linter`         | `file_path: str`, `linter?: str = "auto"`                                | Run flake8/pylint (Python) or eslint (JS/TS)       |
| `start_dev_server`   | `project_dir: str`, `port?: int = 3000`, `command?: str = "npm run dev"` | Validate project structure, suggest start commands |
| `check_port`         | `port: int`                                                              | Check if TCP port is in use                        |

### Command Execution

| Tool              | Parameters                                                | Description                                                                                  |
| ----------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `execute_shell`   | `command: str`, `working_dir?: str`, `timeout?: int = 30` | Execute shell command (dangerous patterns blocked: `rm -rf /`, `mkfs`, `dd if=`, fork bombs) |
| `get_system_info` | none                                                      | Return OS, arch, Python version, hostname                                                    |

### Docker

| Tool           | Parameters                                                                                         | Description          |
| -------------- | -------------------------------------------------------------------------------------------------- | -------------------- |
| `docker_build` | `dockerfile_path: str`, `image_name: str`, `build_args?: str`                                      | Build Docker image   |
| `docker_run`   | `image_name: str`, `container_name?: str`, `ports?: str`, `env_vars?: str`, `detach?: bool = True` | Run Docker container |
| `docker_stop`  | `container_name: str`                                                                              | Stop container       |
| `docker_logs`  | `container_name: str`, `lines?: int = 100`                                                         | Get container logs   |
| `docker_ps`    | `all_containers?: bool = False`                                                                    | List containers      |

### Connector data

The connector category reads connector instances assigned to the active agent.
Agent-service resolves credentials on an internal authenticated path. The model
receives the data source ID and selected resource names, but it never receives
the connector configuration.

| Tool                       | Parameters                                                                                  | Description                                      |
| -------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `connector_list_resources` | `datasource_id: str`                                                                        | List selected resources for an assigned instance |
| `connector_read`           | `datasource_id: str`, `resource: str`, `query?: str`, `filter?: dict`, `limit?: int = 25` | Read up to 100 records from a selected resource  |

Direct reads support these connector and configuration combinations:

- `source-postgres` with native host, username, password, and database fields.
- `source-mysql`, `source-mssql`, and `source-oracle` with native database
  connection fields. SQL Server supports `unencrypted` and
  `encrypted_trust_server_certificate`; Oracle supports unencrypted thin-driver
  connections using a service name or SID. Other encryption variants fail closed.
  MySQL supports omitted or `preferred` SSL mode, attempting TLS when available.
  Modes requiring TLS guarantees are unavailable because the current driver's
  authentication handshake can fall back to plaintext.
- `source-elasticsearch` and `source-opensearch` with an endpoint and optional
  basic authentication or API key.
- `source-http-request` with a fixed `base_url` and a `resources` map from each
  selected stream to a relative GET path.
- `source-mongodb-v2` and `source-mongodb` with a connection URI and either a
  database or native `database_configurations` list.
- `source-s3` with a bucket, selected stream globs, and a saved access-key pair.
  An HTTP or HTTPS endpoint supports MinIO. IAM role and ambient host identity
  variants fail closed.
- `source-sftp-bulk` with a host, user, root folder, selected stream globs, and
  either password or private-key authentication.
- `source-kafka` with bootstrap servers and PLAINTEXT, SSL, SASL/PLAIN, or
  SASL/SCRAM authentication. The runtime rejects OAuth, IAM, and custom Java
  key-store variants.
- `source-microsoft-sharepoint` and `source-outlook` with supported saved
  Microsoft Graph client or refresh-token credentials.

PostgreSQL and MongoDB accept scalar equality filters. HTTP Request accepts
scalar GET parameters. Elasticsearch and OpenSearch accept query text. The
runtime rejects free-form SQL and MongoDB expressions, cross-origin HTTP paths,
unapproved redirects, unselected resources, and unsupported configurations. It
caps each result at 100 records and 64 KiB.

For S3 and SFTP Bulk, `connector_list_resources` also returns up to 100 matching
files across the selected streams. Pass `{"key": "orders/2026/file.jsonl"}` as
the S3 `query`, or `{"path": "/exports/orders/file.csv"}` as the SFTP `query`,
to read the first 64 KiB of a matching file. A file must remain inside the saved
stream glob and SFTP root.

Kafka reads manually assign every partition for the selected topic, seek to a
recent bounded offset, and return up to 100 messages. They don't join a consumer
group, enable automatic commits, or commit offsets.

SharePoint supports the explicit `ACCESSIBLE_DRIVES` search scope, an empty
site URL for the main site, or a saved `https://*.sharepoint.com/sites/...` URL.
Other search scopes are unavailable. An empty `query` lists files matching the
selected stream's globs. To read a listed file, pass
`{"drive_id": "listed-drive-id", "path": "relative/file.csv"}` as `query`.
Paths are relative to the saved folder. Traversal stops at 40 requests, eight
folder levels, ten drives, or the requested result limit. Downloads validate
redirect destinations before following and stop at 64 KiB.

Outlook supports `profile`, `mailboxes`, `messages`, `conversations`, and
`messages_details`. The details stream accepts a message ID in `query`;
other streams use an empty query. These Microsoft 365 adapters provide reads
through fixed Microsoft Graph endpoints.

### File Operations

| Tool               | Parameters                                                | Description                         |
| ------------------ | --------------------------------------------------------- | ----------------------------------- |
| `file_read`        | `file_path: str`, `max_lines?: int = 1000`                | Read file content                   |
| `file_write`       | `file_path: str`, `content: str`, `append?: bool = False` | Write or append to file             |
| `file_list`        | `directory: str`, `pattern?: str`                         | List directory (up to 100 items)    |
| `create_directory` | `dir_path: str`, `parents?: bool = True`                  | Create directory                    |
| `file_exists`      | `file_path: str`                                          | Check file/directory existence      |
| `file_update`      | `file_path: str`, `old_text: str`, `new_text: str`        | Replace text in file (1 occurrence) |
| `file_delete`      | `file_path: str`, `recursive?: bool = False`              | Delete file or directory            |

### Git

| Tool             | Parameters                                                                        | Description                 |
| ---------------- | --------------------------------------------------------------------------------- | --------------------------- |
| `git_clone`      | `repo_url: str`, `target_dir?: str`, `branch?: str`                               | Clone repository            |
| `git_pull`       | `repo_dir: str`, `remote?: str = "origin"`, `branch?: str`                        | Pull from remote            |
| `git_push`       | `repo_dir: str`, `remote?: str = "origin"`, `branch?: str`                        | Push to remote              |
| `git_status`     | `repo_dir: str`                                                                   | Show git status             |
| `git_commit`     | `repo_dir: str`, `message: str`, `add_all?: bool = True`                          | Stage all and commit        |
| `git_branch`     | `repo_dir: str`, `branch_name?: str`, `create?: bool = False`                     | List/create/switch branches |
| `git_init`       | `repo_dir: str`, `initial_branch?: str = "main"`                                  | Initialize git repo         |
| `git_remote_add` | `repo_dir: str`, `remote_url: str`, `remote_name?: str = "origin"`                | Add/update remote           |
| `git_log`        | `repo_dir: str`, `max_commits?: int = 10`                                         | Show commit log             |
| `git_config`     | `user_email?: str`, `user_name?: str`, `repo_dir?: str`, `scope?: str = "global"` | Get/set git config          |
| `git_diff`       | `repo_dir: str`, `staged?: bool = False`                                          | Show diff                   |

### Java

| Tool                 | Parameters                                                                                 | Description               |
| -------------------- | ------------------------------------------------------------------------------------------ | ------------------------- |
| `run_jar`            | `jar_path: str`, `args?: str`, `main_class?: str`, `jvm_args?: str`, `timeout?: int = 120` | Run JAR file              |
| `run_java`           | `code: str`, `class_name?: str = "Main"`, `timeout?: int = 60`                             | Compile and run Java code |
| `compile_java_file`  | `file_path: str`, `output_dir?: str`, `timeout?: int = 60`                                 | Compile .java file        |
| `validate_java`      | `code: str`, `class_name?: str = "Main"`                                                   | Validate Java syntax      |
| `validate_java_file` | `file_path: str`                                                                           | Validate Java file        |
| `inspect_jar`        | `jar_path: str`, `show_manifest?: bool = True`                                             | Inspect JAR contents      |

### JSON / Data

| Tool          | Parameters                      | Description                                   |
| ------------- | ------------------------------- | --------------------------------------------- |
| `json_format` | `data: str`, `indent?: int = 2` | Pretty-print JSON                             |
| `json_query`  | `data: str`, `path: str`        | Query JSON by dot path (e.g., `users.0.name`) |

### Mail

The mail category exposes SMTP-backed email sending. Runtime callers must
provide the resolved `smtp_config`; agents receive only the safe `send_email`
schema and never receive SMTP passwords in prompts. Callers can include
attachments as base64 payloads after agent-service has resolved the user's
chat files.

| Tool         | Parameters                                                                                                                                                         | Description                                     |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------- |
| `send_email` | `smtp_config: dict`, `to: str`, `subject: str`, `body: str`, `cc?: str`, `bcc?: str`, `is_html?: bool = False`, `reply_to?: str`, `attachments?: list[dict]` | Send an email through a configured SMTP account |

### Knowledge retrieval

The knowledge category exposes agent-facing retrieval tools backed by
rag-service `POST /api/v1/retrieval`. Agent-service supplies trusted user and
tenant context through tools-service transport headers; model-visible arguments
contain the query. Collection IDs are optional model-visible arguments because
agent-service normally passes them through trusted binding references
(`database_search.collection_ids` and `graph_search.collection_ids`).

| Tool              | Parameters                                                   | Description                                               |
| ----------------- | ------------------------------------------------------------ | --------------------------------------------------------- |
| `database_search` | `query: str`, `collection_ids?: list[str]`, `limit?: int = 5`  | Retrieve document context from configured collections      |
| `graph_search`    | `query: str`, `collection_ids?: list[str]`, `limit?: int = 10` | Retrieve knowledge-graph context from configured collections |

### PDF

| Tool                 | Parameters                                                            | Description                                   |
| -------------------- | --------------------------------------------------------------------- | --------------------------------------------- |
| `read_pdf`           | `file_path: str`, `max_pages?: int`                                   | Extract text from PDF (PyMuPDF)               |
| `read_pdf_page`      | `file_path: str`, `page_number: int`                                  | Extract text from single page                 |
| `get_pdf_info`       | `file_path: str`                                                      | Get PDF metadata (pages, title, author, etc.) |
| `search_pdf`         | `file_path: str`, `search_text: str`, `case_sensitive?: bool = False` | Search text in PDF                            |
| `extract_pdf_tables` | `file_path: str`, `page_number?: int`                                 | Extract tables from PDF                       |

### Service Management

| Tool              | Parameters                                      | Description                                 |
| ----------------- | ----------------------------------------------- | ------------------------------------------- |
| `service_restart` | `service_name: str`, `use_docker?: bool = True` | Restart Docker container or systemd service |

### Text Processing

| Tool             | Parameters                                  | Description                           |
| ---------------- | ------------------------------------------- | ------------------------------------- |
| `text_analysis`  | `text: str`                                 | Return character/word/sentence counts |
| `translate_text` | `text: str`, `target_language?: str = "en"` | Translation placeholder               |

### Time & Date

| Tool               | Parameters       | Description                                                              |
| ------------------ | ---------------- | ------------------------------------------------------------------------ |
| `get_current_time` | `timezone?: str` | Get current time (supports IANA timezones like `UTC`, `Europe/Istanbul`) |

### Utilities

| Tool            | Parameters                                | Description                        |
| --------------- | ----------------------------------------- | ---------------------------------- |
| `generate_uuid` | none                                      | Generate UUID v4                   |
| `encode_base64` | `text: str`                               | Encode to Base64                   |
| `decode_base64` | `encoded: str`                            | Decode from Base64                 |
| `hash_text`     | `text: str`, `algorithm?: str = "sha256"` | Hash text (md5/sha1/sha256/sha512) |

### Web

| Tool            | Parameters                            | Description                                               |
| --------------- | ------------------------------------- | --------------------------------------------------------- |
| `web_search`    | `query: str`, `max_results?: int = 5` | Search web via DuckDuckGo                                 |
| `fetch_webpage` | `url: str`                            | Fetch and clean webpage content (truncated to 8000 chars) |

---

## Auth tiers

| Tier              | Mechanism                                               | Env vars required                                                |
| ----------------- | ------------------------------------------------------- | ---------------------------------------------------------------- |
| 1. Keycloak JWT   | RS256/RS384/RS512 JWT verified against JWKS             | `KEYCLOAK_ISSUER_URL`, `KEYCLOAK_AUDIENCE`, `KEYCLOAK_CLIENT_ID` |
| 2. Internal Token | Verbatim match against `INTERNAL_SERVICE_TOKEN` env var | `INTERNAL_SERVICE_TOKEN`                                         |
| 3. API Keys       | Matched against `VALID_API_KEYS` (comma-separated)      | `VALID_API_KEYS`                                                 |

## Architecture

```
server.py (FastMCP HTTP entrypoint)
  └─ KeycloakTokenVerifier (3-tier auth)
  └─ ToolRegistry
       └─ discover_plugins(src/tools/*_tools.py)  →  17 categories
            ├─ calculator_tools.py
            ├─ code_tools.py
            ├─ command_tools.py
            ├─ docker_tools.py
            ├─ file_tools.py
            ├─ git_tools.py
            ├─ java_tools.py
            ├─ json_tools.py
            ├─ knowledge_tools.py
            ├─ connector_tools.py
            ├─ mail_tools.py
            ├─ pdf_tools.py
            ├─ service_tools.py
            ├─ text_tools.py
            ├─ time_tools.py
            ├─ utility_tools.py
            └─ web_tools.py
```

Each category extends `BaseToolCategory` ABC (`src/core/base.py`), implementing `name`, `description`, `label`, and `register_tools(mcp)`.

## Environment variables

| Variable                 | Default                 | Description                    |
| ------------------------ | ----------------------- | ------------------------------ |
| `MCP_PORT`               | `8001`                  | Server port (Docker: 8003)     |
| `MCP_HOST`               | `0.0.0.0`               | Bind address                   |
| `WORKSPACE_DIR`          | `/workspace`            | Base dir for file/code/git ops |
| `POSTGRES_*`             | —                       | Database connection params     |
| `KEYCLOAK_ISSUER_URL`    | —                       | Keycloak realm issuer          |
| `INTERNAL_SERVICE_TOKEN` | —                       | Service-to-service auth        |
| `VALID_API_KEYS`         | —                       | Comma-separated API keys       |
| `USER_SERVICE_URL`       | `http://localhost:8090` | For permission resolution      |
