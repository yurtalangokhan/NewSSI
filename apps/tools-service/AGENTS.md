# Tools service index

Use this file only for work under `apps/tools-service/`. Root `AGENTS.md` owns
the workflow; this file routes MCP tool work to code, tests, and documentation.

## Ownership and source map

Tools service owns reusable MCP tools and the trusted invocation boundary used
by agent-service.

```text
server.py                       FastMCP entrypoint
src/core/base.py                BaseToolCategory
src/core/registry.py            Plugin discovery and registration
src/core/trusted*.py            Trusted invocation context and middleware
src/core/auth*.py               Auth and authorization
src/core/settings.py            Configuration
src/tools/*_tools.py            Auto-discovered tool categories
src/tools/response.py           Tool response helpers
src/tools/knowledge_tools.py    RAG-backed tools
src/models/                     Permission catalog
tests/test_registry.py          Registry tests
tests/test_*_tools.py           Category tests
```

## Task routing

Use the narrowest row that matches the task.

| Change | Start in | Direct tests |
|---|---|---|
| Existing tool | Matching `src/tools/*_tools.py` | Matching `tests/test_*_tools.py` |
| New category | `src/core/base.py`, nearest category | Registry plus category tests |
| Discovery or startup | `src/core/registry.py`, `server.py` | `tests/test_registry.py` |
| Trusted context | `src/core/trusted*.py` | Trusted-context tests |
| Knowledge retrieval | `src/tools/knowledge_tools.py` | `tests/test_knowledge_tools.py` |
| Permissions | `src/models/` and auth boundary | Matching authorization tests |

## Documentation routing

Open only a document whose condition matches the change.

| Condition | Document |
|---|---|
| Tool schema, output, or public contract changes | `docs/api.md` |
| Registry, trust, or service boundary changes | `docs/architecture.md` |
| Test scope is unclear | `docs/testing.md` |
| Startup, environment, or operations change | `docs/runbook.md` |
| Service ownership is unclear | `docs/overview.md` |

## Invariants

- Every tool category extends `BaseToolCategory` and uses registry discovery.
- Tool modules end in `_tools.py`; do not add standalone tool modules.
- Preserve `ToolRegistry.discover_plugins()` and the `server.py` entrypoint.
- Keep trusted credentials out of model-visible arguments.
- Keep retrieval implementation in RAG service; this service exposes knowledge
  tools only.
- Use Ruff line length 100 and the existing response helpers.

## Test scope

Use `uv run pytest <matching-test-path>` inside quiet task/spec wrappers. Add
agent-service gateway tests only when the cross-service contract changes. Full
`make validate` runs only through the push wrapper.
