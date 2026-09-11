# Tools service runbook

Use this runbook for local startup and operational checks.

## Startup

Run these commands from `apps/tools-service/`.

```sh
make dev-install
make run
```

The direct FastMCP transport defaults to `MCP_PORT=8001`; Docker and Kong can
map the service to different ports. Use environment configuration instead of
hardcoded ports.

## Health

Use `GET /health` directly or the Kong service path documented in
[api.md](api.md). Tool discovery and execution use the MCP transport at `/mcp`.
