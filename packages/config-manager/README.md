# config_manager

Shared central environment loading for the Agentic AI backend services.

- `config_manager.manager.load_environment()` loads `configs/.env` once per process,
  preserving existing process variables. The file is
  resolved without depending on the working directory; `AGENTICAI_ENV_FILE`
  selects an explicit file for deployments and isolated tests.
- `config_manager.accessor` exposes the shared typed accessor:
  `from config_manager import env`. Uppercase properties mirror configuration keys.

Backend services consume this accessor directly. The central file never
overrides values already present in the process environment.

Internal service URLs use `INTERNAL_TOOLS_SERVICE_URL`,
`INTERNAL_RAG_SERVICE_API_URL`, `INTERNAL_USER_SERVICE_URL`, and
`INTERNAL_AGENT_SERVICE_URL`. The agent URL includes `/api/v1` for connector
resolution. The shared
`INTERNAL_SERVICE_TOKEN` authenticates internal calls. The catalog keeps these
separate from web runtime `AGENT_SERVICE_URL`, `USER_SERVICE_URL`, and
`RAG_SERVICE_URL`; each accessor reads its exact key without fallback aliases.
Existing unprefixed accessor properties remain available for web and public
metadata. Backend clients use the prefixed properties and do not fall back to
web URLs. Set the required internal URLs before starting backend services.
