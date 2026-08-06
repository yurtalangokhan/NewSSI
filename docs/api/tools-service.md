# Tools Service (MCP Server) API

**Service:** MCP (Model Context Protocol) tool server — code execution, file operations, git, search, Docker, and more.
**Base URL:** `http://kong:8000/tools-service/mcp` (via Kong, JWT required) or `http://tools-service:8003/mcp` (direct)
**Auth:** 3-tier — JWT (Keycloak) > Internal Token > API Key. All tools require `tool:execute` scope.

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

## Tool categories

15 tool categories auto-discovered at startup via `ToolRegistry.discover_plugins()`.

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
       └─ discover_plugins(src/tools/*_tools.py)  →  15 categories
            ├─ calculator_tools.py
            ├─ code_tools.py
            ├─ command_tools.py
            ├─ docker_tools.py
            ├─ file_tools.py
            ├─ git_tools.py
            ├─ java_tools.py
            ├─ json_tools.py
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
