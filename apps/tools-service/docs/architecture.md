# Tools service architecture

Tools service exposes tool categories through FastMCP. Each category implements
the shared `BaseToolCategory` contract and registers tools through the central
registry.

## Runtime flow

```text
server.py -> ToolRegistry -> BaseToolCategory implementations -> tool functions
```

`ToolRegistry.discover_plugins()` loads categories from `src/tools/` at startup.
Categories own schemas, permission metadata, and execution logic for their
tools.

## Agent boundary

Agent service must not reimplement generic tools locally. Add reusable tools in
tools-service, add tests in this service, then expose them to agents through the
agent-service tool gateway and trusted binding context.

## Knowledge tools

`src/tools/knowledge_tools.py` owns `database_search` and `graph_search`. These
tools call rag-service retrieval endpoints and keep collection/user context
outside model-visible arguments when agent-service supplies trusted bindings.
