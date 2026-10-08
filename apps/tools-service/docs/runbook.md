# Tools service runbook

Use this runbook for local startup and operational checks.

## Startup

Run these commands from `apps/tools-service/`.

```sh
make dev-install
make run
```

The direct FastMCP transport defaults to `MCP_PORT=8001`; Docker and the
gateway can map the service to different ports. Use environment configuration instead of
hardcoded ports.

Set `INTERNAL_USER_SERVICE_URL` for permission calls and
`INTERNAL_RAG_SERVICE_API_URL` for knowledge retrieval. Connector tools use
`INTERNAL_AGENT_SERVICE_URL`, including `/internal/agent-service/api/v1`,
and `INTERNAL_SERVICE_TOKEN`. These clients do not fall back to web runtime
URLs. Public MCP metadata continues to use `MCP_PUBLIC_BASE_URL` or
`TOOLS_SERVICE_URL`.

The PostgreSQL pool is opened on first use. With `POSTGRES_ADMIN_USER` and
`POSTGRES_ADMIN_PASSWORD` set, the service then creates its login role
(`POSTGRES_TOOL_SERVICE_USER`, password set to the configured one on every
start) and its database (`POSTGRES_TOOL_SERVICE_DB`, owned by that role) when
they are missing, as the other services' bootstrap migrations do. Without the
admin credentials the role has to exist already and hold `CREATEDB`.

## Health

Use `GET /health` directly or the gateway service path documented in
[api.md](api.md). Tool discovery and execution use the MCP transport at `/mcp`.
