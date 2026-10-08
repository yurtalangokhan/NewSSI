# RAG service overview

RAG service owns retrieval, document processing, vector collections, and graph
RAG storage. Agent service reaches RAG through tools-service knowledge tools for
agent-facing retrieval.

## Source map

Organised by domain — see `AGENTS.md` for the full routing table.

| Area | Location |
|---|---|
| Collection metadata | `src/collections/` |
| Documents, chunks, upload pipeline | `src/documents/` |
| Connector-managed collections | `src/datasources/` |
| Knowledge graph | `src/graph/` |
| Unified agent-facing retrieval | `src/retrieval/` |
| Cross-cutting infra (auth, config, DB/vector-store factories) | `src/shared/` |
| Tests | `tests/` |

## Documentation

- [Architecture](architecture.md) describes service boundaries and data flow.
- [API](api.md) lists endpoint contracts.
- [Testing](testing.md) describes validation commands.
- [Runbook](runbook.md) covers startup and operational checks.
