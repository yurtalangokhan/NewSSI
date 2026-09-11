# Agent Service Composition

This document describes how agents are constructed and run in the agent-service
after the `agent-service-composition` workstream (ASC-0 … ASC-7). It is the
authoritative reference for the final runtime. The older monolithic agent
modules were verified orphaned and removed in ASC-7.

## Canonical construction path

All agents — built-in and persisted dynamic definitions — are composed through
the `agent_composition` package:

1. `AgentFactory.create(definition, execution_context)` is the single
   application entrypoint for building a new executable agent. It validates the
   definition, asks `AgentComposer` for an unloaded runtime, awaits
   `ComposedAgent.load()`, and returns the loaded runtime.
2. `AgentComposer` applies builder semantics: it resolves lazy component
   providers (brain, perceptrons, tool gateway, graph schema, runtime
   policies), validates compatibility, and assembles an unloaded
   `ComposedAgent`. It never opens network, model, store, or graph resources.
3. `ComposedAgent` is the sole owner of acquired runtime resources. Its
   idempotent `load()` / `close()` acquire and release them; it exposes
   `ainvoke`, `astream`, `astream_events`, `aget_state`, `aupdate_state`, and
   `aget_state_history`.

These classes live in:

- `src/agent_composition/application/compose_agent.py` — `AgentFactory`, `AgentComposer`
- `src/agent_composition/runtime/composed_agent.py` — `ComposedAgent`
- `src/agent_composition/domain/ports.py` — `Brain`, `Perceptron`, `ToolGateway`, `GraphSchemaStrategy`, `RuntimePolicy`, `ExecutableAgent`
- `src/agent_composition/runtime/` — lifecycle, checkpoint, memory, safety, retry policies

## Component selection

Definitions store stable component keys, never Python class paths. Components
are resolved through:

- `src/agent_composition/domain/component_catalog.py` — `COMPONENT_CATALOG` and `get_component`
- `src/agent_composition/domain/definitions.py` — `AgentDefinition`, `BrainConfig`, `GraphSchemaConfig`, `PerceptronConfig`, `ToolSelection`, `RuntimePolicyConfig`

## Graph schemas

Each graph topology is a `GraphSchemaStrategy` registered in
`GraphSchemaStrategyRegistry` (`src/agents/graphs/strategies/registry.py`).
Strategies live in `src/agents/graphs/strategies/`: `zero_shot`, `react`,
`supervisor`, `pipeline`, `plan_execute`, `self_reflect`. `GraphBuilder`
(`src/agents/graphs/builder.py`) selects a strategy by key. Pipeline stage order
is deterministic, not prompt-driven.

## Tool gateway

Tools-service owns platform tool implementations. Agent-service selects tools
and supplies trusted invocation context; it must not add new generic tool
implementations under `src/agents/`. The `ToolGateway` port is implemented by
`ToolsServiceToolGateway`
(`src/agent_composition/adapters/tools_service_gateway.py`), which resolves
remote tool handles from tools-service. The trusted invocation context
(`src/agent_composition/domain/trusted_context.py`) keeps credentials and
internal binding references out of model-visible arguments.

The generic calculator tool is owned by tools-service
(`apps/tools-service/src/tools/calculator_tools.py`). Agent-service no longer
keeps a local calculator implementation.

Knowledge retrieval follows the same boundary. Agent-service maps an agent's
`rag_config` to the tools-service tool names `database_search` and
`graph_search`, and passes collection IDs through trusted binding references
such as `database_search.collection_ids`. The retrieval implementation lives in
`apps/tools-service/src/tools/knowledge_tools.py`, which calls rag-service
`POST /api/v1/retrieval`. Agent-service no longer keeps local
`database_search` or `graph_search` LangChain tool wrappers.

## Built-in agents and Studio

Built-in agents are recipes over the same composer used by persisted dynamic
agents:

- `src/agent_composition/application/recipes.py` — `BUILTIN_RECIPES` maps
  `chatbot`, `configurable-mcp-agent`, `pipeline`, `supervisor` to flat
  definition configs. Recipes don't pin a model; runtime provider/default-model
  resolution chooses the model unless a caller supplies an explicit override.
  `get_builtin_recipe(agent_id)` resolves one.
- `src/agents/agents.py` — the backward-compatible static registry facade.
  `chatbot` and `configurable-mcp-agent` are served from the static registry;
  `pipeline` and `supervisor` (recipe-only) are composed via `AgentFactory`.
- `src/agents/studio_graphs.py` — LangGraph Studio entrypoints. Each is a
  callable that builds a compiled graph from a model-agnostic recipe via
  `GraphBuilder`. `langgraph.json` points Studio at `studio_graphs.py` (graphs:
  `chatbot`, `research-assistant`, `rag-assistant`,
  `graph-rag-assistant`).

## Removed legacy modules (ASC-7)

The following were verified orphaned (no production or test importer) and
deleted in ASC-7:

- `src/agents/research_assistant.py`, `rag_assistant.py`, `graph_rag_assistant.py`
- `src/agents/factory/` — reflection `AgentFactory` reading class paths from JSON
- `src/agents/registry/` — legacy `@agent` registry
- `src/agents/configs/` — JSON configs for the reflection factory
- `src/agents/managers/` — duplicate supervisor/pipeline managers
- `src/agents/runtime/` — orphaned `instance_manager` that selected managers by name
- `src/agents/base/` — disconnected abstract agent/brain/perceptron/manager contracts
- `src/agents/impl/` — legacy chatbot implementation no longer used by the static registry
- `src/agents/perceptrons/` — disconnected MCP/composite perceptron implementations
- `src/agents/command_agent.py`, `interrupt_agent.py`, `knowledge_base_agent.py`
- `src/agents/langgraph_supervisor_agent.py`, `langgraph_supervisor_hierarchy_agent.py`
- `src/agents/bg_task_agent/` — demo background-task graph outside the FastAPI
  registry and Studio entrypoints

## Retained local tool modules

The following local tool modules are still used by the live graph strategies
and ingestion/data paths, so they were intentionally retained (verification-first
deletion rule: do not delete a module with live importers):

- `src/agents/document_tools.py` — used by `graphs/strategies/*`, `graphs/builder.py`, `chatbot.py`, `configurable_mcp_agent.py`, and their tests.
- `src/agents/mail_tooling.py` — used by `graphs/strategies/*`, `graphs/builder.py`, `configurable_mcp_agent.py`.
- `src/agents/tools.py` — Milvus/vector-store and embedding helpers used by `IngestService`, `data_controller`, `DatasourcesRoute`, and `core/db/repositories/datasource_repo.py`.

Moving these behind tools-service / RAG-service contracts remains active
simplification work. ASC-2 laid the trusted-context foundation, and new generic
tools must be implemented in tools-service first, then exposed to agents through
`ToolsServiceToolGateway`.

`src/agents/tools.py` no longer contains local calculator, user-context,
`database_search`, or `graph_search` tool implementations. Milvus and embedding
helpers remain only because current ingestion and datasource inspection paths
still depend on them.

## Package exports

`src/agents/__init__.py` re-exports only the backward-compatible facade
(`get_agent`, `load_agent`, `get_all_agent_info`, `DEFAULT_AGENT`,
`AgentGraph`, `AgentGraphLike`). Persistence now lives in
`src/core/db/models/agent_definition.py` and
`src/repository/agent_definition_repository.py`; it is no longer exported from
the runtime `agents` package. The deleted island packages are no longer
re-exported.
