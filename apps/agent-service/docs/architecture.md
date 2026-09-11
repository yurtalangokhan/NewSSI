# Agent service architecture

Agent service separates HTTP delivery from runtime agent construction. New
agent behavior must extend composition components, graph strategies, recipes, or
tools-service tools instead of adding isolated agent modules.

## Request flow

Agent requests enter through FastAPI routes, move through controller and service
layers, and create executable agents through the composition package.

```text
api/routes -> controller -> service -> AgentFactory -> AgentComposer -> ComposedAgent
```

`ComposedAgent` owns runtime resources after `load()`. It exposes invoke,
stream, event stream, state, and history operations to the service layer.

## Dynamic agents

Dynamic agent definitions are persisted through
`src/repository/agent_definition_repository.py` and stored with the database
models in `src/core/db/models/agent_definition.py`. Definitions store stable
component keys, graph schema names, tool selections, and runtime policy config.
They don't store Python class paths or hardcoded model names.

## Built-in agents

Built-in agents are recipes in
`src/agent_composition/application/recipes.py`. Recipes must stay
model-agnostic unless a caller explicitly supplies a model override. Runtime
provider and default-model resolution choose the actual model.

## Tools boundary

Tools-service owns reusable tool implementations. Agent service selects tools,
passes trusted invocation context, and calls tools through
`ToolsServiceToolGateway`. Do not add new generic tools under
`src/agents/`.

Knowledge retrieval follows this boundary: agent service maps `rag_config` to
the tools-service `database_search` and `graph_search` tools, and tools-service
calls rag-service retrieval endpoints.
