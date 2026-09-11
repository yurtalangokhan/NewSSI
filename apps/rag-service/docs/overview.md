# RAG service overview

RAG service owns retrieval, document processing, vector collections, and graph
RAG storage. Agent service reaches RAG through tools-service knowledge tools for
agent-facing retrieval.

## Source map

| Area | Location |
|---|---|
| FastAPI routers | `langconnect/api/` |
| Business services | `langconnect/services/` |
| Database and stores | `langconnect/database/` |
| Pydantic models | `langconnect/models/` |
| Tests | `tests/` |

## Documentation

- [Architecture](architecture.md) describes service boundaries and data flow.
- [API](api.md) lists endpoint contracts.
- [Testing](testing.md) describes validation commands.
- [Runbook](runbook.md) covers startup and operational checks.
