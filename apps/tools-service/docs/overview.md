# Tools service overview

Tools service owns reusable MCP tool implementations. Agent service consumes
these tools through a gateway and passes trusted invocation context instead of
embedding generic tool logic in agent modules.

## Source map

| Area | Location |
|---|---|
| FastMCP entrypoint | `server.py` |
| Registry and base contracts | `src/core/` |
| Tool categories | `src/tools/` |
| Permission catalog | `src/models/` |
| Tests | `tests/` |

## Documentation

- [Architecture](architecture.md) describes registry and tool ownership.
- [API](api.md) lists MCP transport and tool contracts.
- [Testing](testing.md) describes validation commands.
- [Runbook](runbook.md) covers startup and operational checks.
